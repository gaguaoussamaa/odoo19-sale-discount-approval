from odoo import fields, models


class SaleDiscountRefuseWizard(models.TransientModel):
    _name = 'sale.discount.refuse.wizard'
    _description = "Refus d'une remise sur devis"

    order_id = fields.Many2one('sale.order', string="Devis", required=True, readonly=True, ondelete='cascade')
    reason = fields.Text(string="Motif du refus", required=True)

    def action_refuse(self):
        self.ensure_one()
        self.order_id._refuse_discount(self.reason)
        return {'type': 'ir.actions.act_window_close'}
