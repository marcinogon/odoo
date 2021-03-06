# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.tools import float_compare


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    sale_name = fields.Char(compute='_compute_sale_name_sale_ref', string='Sale Name', help='Indicate the name of sales order.')
    sale_ref = fields.Char(compute='_compute_sale_name_sale_ref', string='Sale Reference', help='Indicate the Customer Reference from sales order.')

    def _get_parent_move(self, move):
        if move.move_dest_id:
            return self._get_parent_move(move.move_dest_id)
        return move

    @api.multi
    def _compute_sale_name_sale_ref(self):
        for production in self:
            move = production._get_parent_move(production.move_finished_ids[0])
            production.sale_name = move.procurement_id and move.procurement_id.sale_line_id and move.procurement_id.sale_line_id.order_id.name or False
            production.sale_ref = move.procurement_id and move.procurement_id.sale_line_id and move.procurement_id.sale_line_id.order_id.client_order_ref or False


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.multi
    def _get_delivered_qty(self):
        self.ensure_one()

        # In the case of a kit, we need to check if all components are shipped. Since the BOM might
        # have changed, we don't compute the quantities but verify the move state.
        bom = self.env['mrp.bom']._bom_find(product=self.product_id)
        if bom and bom.type == 'phantom':
            bom_delivered = all([move.state == 'done' for move in self.procurement_ids.mapped('move_ids')])
            if bom_delivered:
                return self.product_uom_qty
            else:
                return 0.0
        return super(SaleOrderLine, self)._get_delivered_qty()


class AccountInvoiceLine(models.Model):
    # TDE FIXME: what is this code ??
    _inherit = "account.invoice.line"

    def _get_anglo_saxon_price_unit(self):
        price_unit = super(AccountInvoiceLine, self)._get_anglo_saxon_price_unit()
        # in case of anglo saxon with a product configured as invoiced based on delivery, with perpetual
        # valuation and real price costing method, we must find the real price for the cost of good sold
        if self.product_id.invoice_policy == "delivery":
            for s_line in self.sale_line_ids:
                # qtys already invoiced
                qty_done = sum([x.uom_id._compute_quantity(x.quantity, x.product_id.uom_id) for x in s_line.invoice_lines if x.invoice_id.state in ('open', 'paid')])
                quantity = self.uom_id._compute_quantity(self.quantity, self.product_id.uom_id)
                # Put moves in fixed order by date executed
                moves = self.env['stock.move']
                for procurement in s_line.procurement_ids:
                    moves |= procurement.move_ids
                moves.sorted(lambda x: x.date)
                # Go through all the moves and do nothing until you get to qty_done
                # Beyond qty_done we need to calculate the average of the price_unit
                # on the moves we encounter.
                bom = s_line.product_id.product_tmpl_id.bom_ids and s_line.product_id.product_tmpl_id.bom_ids[0]
                if bom.type == 'phantom':
                    average_price_unit = 0
                    components = s_line._get_bom_component_qty(bom)
                    for product_id in components:
                        factor = components[product_id]['qty']
                        prod_moves = [m for m in moves if m.product_id.id == product_id]
                        prod_qty_done = factor * qty_done
                        prod_quantity = factor * quantity
                        average_price_unit += self._compute_average_price(prod_qty_done, prod_quantity, prod_moves)
                    price_unit = average_price_unit or price_unit
                    price_unit = self.product_id.uom_id._compute_price(price_unit, self.uom_id)
        return price_unit
