from odoo import api, fields, models, tools, SUPERUSER_ID, _
import logging
import os
_logger = logging.getLogger(__name__)
wkhtmltopdf_dpi_zoom_ratio = False

class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'
    @api.model
    def _build_wkhtmltopdf_args(
            self,
            paperformat_id,
            landscape,
            specific_paperformat_args=None,
            set_viewport_size=False):
        '''Build arguments understandable by wkhtmltopdf bin.

        :param paperformat_id: A report.paperformat record.
        :param landscape: Force the report orientation to be landscape.
        :param specific_paperformat_args: A dictionary containing prioritized wkhtmltopdf arguments.
        :param set_viewport_size: Enable a viewport sized '1024x1280' or '1280x1024' depending of landscape arg.
        :return: A list of string representing the wkhtmltopdf process command args.
        '''
        if landscape is None and specific_paperformat_args and specific_paperformat_args.get('data-report-landscape'):
            landscape = specific_paperformat_args.get('data-report-landscape')

        command_args = ['--enable-local-file-access']
        if set_viewport_size:
            command_args.extend(['--viewport-size', landscape and '1024x1280' or '1280x1024'])

        # Less verbose error messages
        command_args.extend(['--quiet'])

        # Build paperformat args
        if paperformat_id:
            if paperformat_id.format and paperformat_id.format != 'custom':
                command_args.extend(['--page-size', paperformat_id.format])

            if paperformat_id.page_height and paperformat_id.page_width and paperformat_id.format == 'custom':
                command_args.extend(['--page-width', str(paperformat_id.page_width) + 'mm'])
                command_args.extend(['--page-height', str(paperformat_id.page_height) + 'mm'])

            if specific_paperformat_args and specific_paperformat_args.get('data-report-margin-top'):
                command_args.extend(['--margin-top', str(specific_paperformat_args['data-report-margin-top'])])
            else:
                command_args.extend(['--margin-top', str(paperformat_id.margin_top)])

            dpi = None
            if specific_paperformat_args and specific_paperformat_args.get('data-report-dpi'):
                dpi = int(specific_paperformat_args['data-report-dpi'])
            elif paperformat_id.dpi:
                if os.name == 'nt' and int(paperformat_id.dpi) <= 95:
                    _logger.info("Generating PDF on Windows platform require DPI >= 96. Using 96 instead.")
                    dpi = 96
                else:
                    dpi = paperformat_id.dpi
            if dpi:
                command_args.extend(['--dpi', str(dpi)])
                if wkhtmltopdf_dpi_zoom_ratio:
                    command_args.extend(['--zoom', str(96.0 / dpi)])

            if specific_paperformat_args and specific_paperformat_args.get('data-report-header-spacing'):
                command_args.extend(['--header-spacing', str(specific_paperformat_args['data-report-header-spacing'])])
            elif paperformat_id.header_spacing:
                command_args.extend(['--header-spacing', str(paperformat_id.header_spacing)])

            command_args.extend(['--margin-left', str(paperformat_id.margin_left)])

            if specific_paperformat_args and specific_paperformat_args.get('data-report-margin-bottom'):
                command_args.extend(['--margin-bottom', str(specific_paperformat_args['data-report-margin-bottom'])])
            else:
                command_args.extend(['--margin-bottom', str(paperformat_id.margin_bottom)])

            command_args.extend(['--margin-right', str(paperformat_id.margin_right)])
            if not landscape and paperformat_id.orientation:
                command_args.extend(['--orientation', str(paperformat_id.orientation)])
            if paperformat_id.header_line:
                command_args.extend(['--header-line'])
            if paperformat_id.disable_shrinking:
                command_args.extend(['--disable-smart-shrinking'])

        # Add extra time to allow the page to render
        delay = self.env['ir.config_parameter'].sudo().get_param('report.print_delay', '1000')
        command_args.extend(['--javascript-delay', delay])

        if landscape:
            command_args.extend(['--orientation', 'landscape'])

        return command_args