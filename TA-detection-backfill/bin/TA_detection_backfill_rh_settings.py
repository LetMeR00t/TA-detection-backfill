
import ta_detection_backfill_declare

from splunktaucclib.rest_handler.endpoint import (
    field,
    validator,
    RestModel,
    MultipleModel,
)
from splunktaucclib.rest_handler import admin_external, util
from splunk_aoblib.rest_migration import ConfigMigrationHandler

util.remove_http_proxy_env_vars()


fields_logging = [
    field.RestField(
        'loglevel',
        required=False,
        encrypted=False,
        default='INFO',
        validator=None
    )
]
model_logging = RestModel(fields_logging, name='logging')

fields_additional_parameters = [
    field.RestField(
        'dispatch_ttl',
        required=True,
        encrypted=False,
        default='86400',
        validator=validator.Number(
            min_val=60, 
            max_val=31536000, 
        )
    ),
    field.RestField(
        'index_results',
        required=True,
        encrypted=False,
        default='main',
        validator=validator.String(
            min_len=1, 
            max_len=8192, 
        )
    )
]
model_additional_parameters = RestModel(fields_additional_parameters, name='additional_parameters')

endpoint = MultipleModel(
    'ta_detection_backfill_settings',
    models=[
        model_logging,
        model_additional_parameters
    ],
)


if __name__ == '__main__':
    admin_external.handle(
        endpoint,
        handler=ConfigMigrationHandler,
    )
