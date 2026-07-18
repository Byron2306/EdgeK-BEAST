from app.kernel.compute.module_dispositions import disposition_report


def test_every_present_compute_module_has_one_explicit_disposition():
    report = disposition_report()
    assert report["all_present_modules_classified"] is True
    assert report["unclassified"] == []
    assert report["missing_classified_modules"] == []
    categories = [set(report[name]) for name in ("online_enforcement", "supervised_evidence", "offline_library")]
    assert not (categories[0] & categories[1] or categories[0] & categories[2] or categories[1] & categories[2])


def test_duplicate_integration_registry_is_retired():
    report = disposition_report()
    assert "crystal_integrations" in report["retired"]
