from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sale_discount_approval_threshold = fields.Float(
        related='company_id.sale_discount_approval_threshold',
        readonly=False,
    )
