"""Phase 4 regression tests found during the Phase 4/5 audit (config strictness, missing-value handling)."""
import copy

import numpy as np
import pandas as pd
import pytest

from ml.business import BusinessEngine, compute_clv_for_record, load_business_config, parse_business_config
from ml.config import load_config
from ml.errors import BusinessConfigError, BusinessInputError


def parse(mutate):
    raw, bands = copy.deepcopy(load_config("business")), load_config("risk_bands")
    mutate(raw)
    return parse_business_config(raw, bands)


@pytest.mark.parametrize("bad", ["false", "no", 0, 1, None, "true"])
def test_action_enabled_must_be_a_real_boolean(bad):
    """bool('false') is True: a quoted 'false' used to silently re-enable a disabled (costly) action."""
    with pytest.raises(BusinessConfigError, match=r"enabled must be true or false"):
        parse(lambda r: r["actions"]["loyalty_offer"].update(enabled=bad))


@pytest.mark.parametrize("bad", ["no", "false", 0, None])
def test_allow_default_lifetime_must_be_a_real_boolean(bad):
    with pytest.raises(BusinessConfigError, match="allow_default_lifetime must be true or false"):
        parse(lambda r: r["clv"].update(allow_default_lifetime=bad))


def test_real_booleans_are_still_accepted():
    cfg = parse(lambda r: (r["actions"]["loyalty_offer"].update(enabled=False),
                           r["clv"].update(allow_default_lifetime=False)))
    assert cfg.actions["loyalty_offer"].enabled is False and cfg.clv.allow_default_lifetime is False


def test_non_mapping_action_is_a_config_error_not_an_attribute_error():
    with pytest.raises(BusinessConfigError, match="actions.broken must be a mapping"):
        parse(lambda r: r["actions"].update(broken=5))


@pytest.mark.parametrize("missing", [pd.NA, np.float32("nan"), np.float64("nan"), float("nan"), None, "  "])
def test_every_flavour_of_missing_revenue_gets_the_missing_message(missing):
    cfg = load_business_config()
    with pytest.raises(BusinessInputError, match="is required to compute CLV and is missing"):
        compute_clv_for_record({"MonthlyCharges": missing, "Contract": "Two year"}, cfg.clv)


def test_nullable_dtype_frame_with_missing_revenue_is_rejected_clearly():
    frame = pd.DataFrame({"MonthlyCharges": pd.array([50.0, None], dtype="Float64"),
                          "Contract": ["One year", "One year"]})
    engine = BusinessEngine(load_business_config(), 0.34)
    with pytest.raises(BusinessInputError, match="missing"):
        engine.profile_frame(frame, [0.5, 0.5])
