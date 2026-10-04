from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    sale_discount_approval_threshold = fields.Float(
        string="Seuil de remise à valider (%)",
        digits='Discount',
        default=10.0,
        help="Au-delà de cette remise effective, un devis doit être validé "
             "par un responsable avant confirmation.",
    )

    _check_sale_discount_approval_threshold = models.Constraint(
        'CHECK(sale_discount_approval_threshold >= 0 '
        'AND sale_discount_approval_threshold <= 100)',
        "Le seuil de remise doit être compris entre 0 et 100 %.",
    )
