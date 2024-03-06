
# encoding = utf-8
# Always put this line at the beginning of this file
import ta_detection_backfill_declare

import os
import sys

from alert_actions_base import ModularAlertBase
import modalert_detection_backfill_add_a_backfill_to_the_backlog_helper

class AlertActionWorkerdetection_backfill_add_a_backfill_to_the_backlog(ModularAlertBase):

    def __init__(self, ta_name, alert_name):
        super(AlertActionWorkerdetection_backfill_add_a_backfill_to_the_backlog, self).__init__(ta_name, alert_name)

    def validate_params(self):

        if not self.get_param("batch_name"):
            self.log_error('batch_name is a mandatory parameter, but its value is None.')
            return False

        if not self.get_param("batch_priority"):
            self.log_error('batch_priority is a mandatory parameter, but its value is None.')
            return False

        if not self.get_param("savedsearch_field_name"):
            self.log_error('savedsearch_field_name is a mandatory parameter, but its value is None.')
            return False

        if not self.get_param("app_field_name"):
            self.log_error('app_field_name is a mandatory parameter, but its value is None.')
            return False

        if not self.get_param("dispatch_time_field_name"):
            self.log_error('dispatch_time_field_name is a mandatory parameter, but its value is None.')
            return False
        
        if not self.get_param("spl_code_injection"):
            self.log_error('spl_code_injection is a mandatory parameter, but its value is None.')
            return False
        
        return True

    def process_event(self, *args, **kwargs):
        status = 0
        try:
            if not self.validate_params():
                return 3
            status = modalert_detection_backfill_add_a_backfill_to_the_backlog_helper.process_event(self, *args, **kwargs)
        except (AttributeError, TypeError) as ae:
            self.log_error("Error: {}. Please double check spelling and also verify that a compatible version of Splunk_SA_CIM is installed.".format(str(ae)))
            return 4
        except Exception as e:
            msg = "Unexpected error: {}."
            if e:
                self.log_error(msg.format(str(e)))
            else:
                import traceback
                self.log_error(msg.format(traceback.format_exc()))
            return 5
        return status

if __name__ == "__main__":
    exitcode = AlertActionWorkerdetection_backfill_add_a_backfill_to_the_backlog("TA-detection-backfill", "detection_backfill_add_a_backfill_to_the_backlog").run(sys.argv)
    sys.exit(exitcode)
