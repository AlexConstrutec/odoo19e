// Archivo: static/src/js/hr_payslip_prestaciones_button.js

odoo.define('nomina.hrPayslipPrestacionesTreeView', function (require) {
    "use strict";

    var ListController = require('web.ListController');
    var viewRegistry = require('web.view_registry');
    var ListView = require('web.ListView');

    var HrPayslipPrestacionesListController = ListController.extend({
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            if (this.$buttons) {
                this.$buttons.find('.o_list_button_add_prestaciones').remove();
            }
            var self = this;
            var $button = $('<button type="button" class="btn btn-primary o_list_button_add_prestaciones">Prestaciones a la Fecha</button>');
            $button.on('click', function () {
                self.do_action('nomina.action_prestaciones_wizard', {
                    on_close: self.reload.bind(self, {}),
                });
            });
            this.$buttons.append($button);
        }
    });

    var HrPayslipPrestacionesListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: HrPayslipPrestacionesListController,
        }),
    });

    viewRegistry.add('hrPayslipPrestacionesTreeView', HrPayslipPrestacionesListView);
});
