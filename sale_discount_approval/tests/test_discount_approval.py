from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSaleDiscountApproval(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.sale_discount_approval_threshold = 10.0
        cls.salesman = new_test_user(
            cls.env, login='commercial_remise',
            groups='sales_team.group_sale_salesman')
        cls.approver = new_test_user(
            cls.env, login='valideur_remise',
            groups='sales_team.group_sale_salesman,sale_discount_approval.group_discount_approver')
        cls.partner = cls.env['res.partner'].create({'name': "Client test"})
        cls.product = cls.env['product.product'].create({'name': "Station test", 'list_price': 1000.0})

    def _create_quote(self, discount):
        """Un devis d'une ligne à 1 000 €, créé par le commercial."""
        return self.env['sale.order'].with_user(self.salesman).create({
            'partner_id': self.partner.id,
            'order_line': [Command.create({
                'product_id': self.product.id,
                'price_unit': 1000.0,
                'discount': discount,
            })],
        })

    def test_below_threshold_no_approval(self):
        order = self._create_quote(discount=5.0)
        self.assertFalse(order.discount_approval_needed)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_confirmation_blocked_above_threshold(self):
        order = self._create_quote(discount=20.0)
        self.assertAlmostEqual(order.discount_rate, 20.0)
        self.assertTrue(order.discount_approval_needed)
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, 'draft')

    def test_confirmation_allowed_after_approval(self):
        order = self._create_quote(discount=20.0)
        order.action_request_discount_approval()
        self.assertEqual(order.discount_approval_state, 'pending')
        order.with_user(self.approver).action_approve_discount()
        self.assertEqual(order.discount_approval_state, 'approved')
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_salesman_cannot_approve(self):
        order = self._create_quote(discount=20.0)
        order.action_request_discount_approval()
        with self.assertRaises(AccessError):
            order.action_approve_discount()

    def test_higher_discount_after_approval_needs_new_approval(self):
        order = self._create_quote(discount=20.0)
        order.action_request_discount_approval()
        order.with_user(self.approver).action_approve_discount()
        order.order_line.discount = 25.0
        self.assertTrue(order.discount_approval_needed)
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_global_discount_counts(self):
        # Le bouton « Remise » en mode remise globale ajoute une ligne négative :
        # elle doit compter dans la remise effective.
        order = self._create_quote(discount=0.0)
        self.assertFalse(order.discount_approval_needed)
        self.env['sale.order.discount'].create({
            'sale_order_id': order.id,
            'discount_type': 'so_discount',
            'discount_percentage': 0.15,
        }).action_apply_discount()
        self.assertAlmostEqual(order.discount_rate, 15.0)
        self.assertTrue(order.discount_approval_needed)
