from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare

DISCOUNT_APPROVER_GROUP = 'sale_discount_approval.group_discount_approver'
DISCOUNT_APPROVAL_ACTIVITY = 'sale_discount_approval.mail_activity_type_discount_approval'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    discount_rate = fields.Float(
        string="Remise effective (%)",
        compute='_compute_discount_rate',
        store=True,
        digits='Discount',
        help="Écart entre le montant hors taxes sans remise et le montant hors taxes "
             "du devis. Couvre les remises de ligne et les remises globales.",
    )
    discount_approval_state = fields.Selection(
        selection=[
            ('pending', "En attente de validation"),
            ('approved', "Validée"),
            ('refused', "Refusée"),
        ],
        string="Validation de la remise",
        copy=False,
        readonly=True,
        tracking=True,
    )
    discount_approved_rate = fields.Float(
        string="Remise validée (%)",
        digits='Discount',
        copy=False,
        readonly=True,
    )
    discount_approval_needed = fields.Boolean(
        string="Validation de la remise requise",
        compute='_compute_discount_approval_needed',
    )

    @api.depends(
        'amount_untaxed',
        'order_line.discount',
        'order_line.price_unit',
        'order_line.product_uom_qty',
    )
    def _compute_discount_rate(self):
        for order in self:
            # Calcul standard : hors taxes, sans remise de ligne,
            # en ignorant les lignes de remise globale et les acomptes.
            undiscounted = order.amount_undiscounted
            if undiscounted > 0:
                rate = (undiscounted - order.amount_untaxed) / undiscounted * 100
                order.discount_rate = max(rate, 0.0)
            else:
                order.discount_rate = 0.0

    @api.depends(
        'state',
        'discount_rate',
        'discount_approval_state',
        'discount_approved_rate',
        'company_id.sale_discount_approval_threshold',
    )
    def _compute_discount_approval_needed(self):
        for order in self:
            order.discount_approval_needed = order._is_discount_approval_needed()

    def _is_discount_approval_needed(self):
        """La remise dépasse le seuil et aucune validation ne la couvre."""
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            return False
        threshold = self.company_id.sale_discount_approval_threshold
        if float_compare(self.discount_rate, threshold, precision_digits=2) <= 0:
            return False
        # Une validation ne couvre que la remise validée : si la remise augmente
        # ensuite, il faut une nouvelle validation.
        covered = (
            self.discount_approval_state == 'approved'
            and float_compare(self.discount_rate, self.discount_approved_rate, precision_digits=2) <= 0
        )
        return not covered

    def _is_discount_approver(self):
        # OdooBot (le superutilisateur technique) est responsable des ventes, donc
        # « valideur » : il ne doit pas valider à la place d'un humain, par exemple
        # quand une tâche planifiée confirme un devis payé en ligne.
        user = self.env.user
        return not user._is_superuser() and user.has_group(DISCOUNT_APPROVER_GROUP)

    def _check_discount_approver(self):
        # Le vrai contrôle : l'attribut groups de la vue ne fait que masquer le bouton.
        if not self._is_discount_approver():
            raise AccessError(_("Seul un valideur de remises peut valider ou refuser une remise."))

    def action_request_discount_approval(self):
        for order in self:
            if not order.discount_approval_needed:
                raise UserError(_("Le devis %s n'a pas besoin de validation.", order.name))
        self.discount_approval_state = 'pending'
        self._schedule_discount_approval_activities()
        return True

    def _schedule_discount_approval_activities(self):
        # Une activité « Validation de remise » pour chaque valideur de la société du devis.
        approvers = self.env.ref(DISCOUNT_APPROVER_GROUP).sudo().all_user_ids.filtered(
            lambda user: user.active and not user.share and not user._is_superuser())
        for order in self:
            for user in approvers.filtered(lambda u: order.company_id in u.company_ids):
                order.activity_schedule(
                    DISCOUNT_APPROVAL_ACTIVITY,
                    user_id=user.id,
                    note=_("Remise effective de %(rate)s %% (seuil : %(threshold)s %%).",
                           rate=f"{order.discount_rate:.2f}",
                           threshold=f"{order.company_id.sale_discount_approval_threshold:.2f}"),
                )

    def action_approve_discount(self):
        self._check_discount_approver()
        for order in self:
            if order.discount_approval_state != 'pending':
                raise UserError(_("Le devis %s n'a pas de demande de validation en attente.", order.name))
            order.write({
                'discount_approval_state': 'approved',
                'discount_approved_rate': order.discount_rate,
            })
        self.activity_unlink([DISCOUNT_APPROVAL_ACTIVITY])
        return True

    def action_refuse_discount(self):
        # Ouvre l'assistant qui demande le motif du refus.
        self._check_discount_approver()
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Refuser la remise"),
            'res_model': 'sale.discount.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _refuse_discount(self, reason):
        self._check_discount_approver()
        for order in self:
            if order.discount_approval_state != 'pending':
                raise UserError(_("Le devis %s n'a pas de demande de validation en attente.", order.name))
            order.discount_approval_state = 'refused'
            # Note interne qui notifie le commercial du devis.
            order.message_post(
                body=_("Remise refusée : %s", reason),
                partner_ids=order.user_id.partner_id.ids,
                subtype_xmlid='mail.mt_note',
            )
        self.activity_unlink([DISCOUNT_APPROVAL_ACTIVITY])

    def _confirmation_error_message(self):
        # Point d'extension prévu par Odoo : action_confirm() l'appelle pour chaque
        # devis, quel que soit le chemin (bouton, signature en ligne, paiement en ligne).
        error = super()._confirmation_error_message()
        if error:
            return error
        if self.discount_approval_needed and not self._is_discount_approver():
            return _(
                "La remise effective de ce devis (%(rate)s %%) dépasse le seuil de "
                "%(threshold)s %% : il doit être validé par un responsable avant confirmation.",
                rate=f"{self.discount_rate:.2f}",
                threshold=f"{self.company_id.sale_discount_approval_threshold:.2f}",
            )
        return False

    def action_confirm(self):
        # Un valideur qui confirme lui-même un devis au-delà du seuil : on enregistre
        # sa validation, pour que tout devis confirmé au-delà du seuil en garde la trace.
        if self._is_discount_approver():
            for order in self.filtered('discount_approval_needed'):
                order.write({
                    'discount_approval_state': 'approved',
                    'discount_approved_rate': order.discount_rate,
                })
        res = super().action_confirm()
        # Le devis est confirmé : les demandes de validation encore ouvertes n'ont plus d'objet.
        self.activity_unlink([DISCOUNT_APPROVAL_ACTIVITY])
        return res
