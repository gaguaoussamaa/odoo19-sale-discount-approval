from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare

DISCOUNT_APPROVER_GROUP = 'sale_discount_approval.group_discount_approver'


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

    def _check_discount_approver(self):
        # Le vrai contrôle : l'attribut groups de la vue ne fait que masquer le bouton.
        if not self.env.user.has_group(DISCOUNT_APPROVER_GROUP):
            raise AccessError(_("Seul un valideur de remises peut valider ou refuser une remise."))

    def action_request_discount_approval(self):
        for order in self:
            if not order.discount_approval_needed:
                raise UserError(_("Le devis %s n'a pas besoin de validation.", order.name))
        self.discount_approval_state = 'pending'
        return True

    def action_approve_discount(self):
        self._check_discount_approver()
        for order in self:
            if order.discount_approval_state != 'pending':
                raise UserError(_("Le devis %s n'a pas de demande de validation en attente.", order.name))
            order.write({
                'discount_approval_state': 'approved',
                'discount_approved_rate': order.discount_rate,
            })
        return True

    def action_refuse_discount(self):
        self._check_discount_approver()
        for order in self:
            if order.discount_approval_state != 'pending':
                raise UserError(_("Le devis %s n'a pas de demande de validation en attente.", order.name))
        self.discount_approval_state = 'refused'
        return True
