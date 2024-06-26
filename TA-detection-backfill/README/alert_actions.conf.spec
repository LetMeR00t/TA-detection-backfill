[detection_backfill_run_the_next_backfill]
python.version = python3
param._cam = <json> Active response parameters.

[detection_backfill_add_a_backfill_to_the_backlog]
python.version = python3
param._cam = <json> Active response parameters.
param.batch_name = <string> Batch name. It's a required parameter. No default value.
param.batch_priority = <string> Batch priority. It's a required parameter. It's default value is 2.
param.savedsearch_field_name = <string> Savedsearch field name. It's a required parameter. It's default value is savedsearch.
param.app_field_name = <string> App field name. It's a required parameter. It's default value is app.
param.dispatch_time_field_name = <string> Dispatch time field name. It's a required parameter. It's default value is dispatch_time.
param.spl_code_injection = <string> ID of a SPL code injection to execute for the given backfill. It's default value is 0 (meaning none)
param.trigger = <string> Indicates if you want to execute or not the triggers (alert actions) associated to the savedsearches. It's default value is 0 (False)

[detection_backfill_run_healthcheck_on_savedsearches]
python.version = python3
param._cam = <json> Active response parameters.

[detection_backfill_index_results_from_sid]
python.version = python3
param._cam = <json> Active response parameters.

[detection_backfill_add_a_healthcheck_task_to_the_backlog]
python.version = python3
param._cam = <json> Active response parameters.
param.batch_priority = <string> Batch priority. It's a required parameter. It's default value is 2.