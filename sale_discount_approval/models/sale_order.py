from odoo import api, fields, models


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
