"""Run V3 and applicable creative/CSV regressions with external analytics disabled."""
import sys
from pathlib import Path
import unittest
import subprocess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import design_studio_intelligence_store as store

MODULES = (
    'tests.test_design_studio_sales_intelligence',
    'tests.test_design_studio_v2', 'tests.test_design_studio_type_contracts',
    'tests.test_design_studio_find_images', 'tests.test_design_studio_generation_handoff',
    'tests.test_design_studio_hero_photography', 'tests.test_design_studio_page',
    'tests.test_sports_categories',
)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


if __name__ == '__main__':
    if len(sys.argv) == 1:
        # Streamlit AppTest suites must not share global UI contexts.
        commands = [*MODULES, 'tests.test_dashboard_home']
        codes = [subprocess.run([sys.executable, __file__, module]).returncode for module in commands]
        sys.exit(0 if not any(codes) else 1)
    loader = unittest.defaultTestLoader
    module = sys.argv[1]
    suite = loader.loadTestsFromName(module)
    if module == 'tests.test_dashboard_home':
        suite = unittest.TestSuite(t for t in flatten(suite) if any(word in t.id().lower() for word in ('design', 'studio', 'csv', 'import_preview')))
        with patch.object(store, 'load_sources', return_value={'products': [], 'lines': []}):
            result = unittest.TextTestRunner(verbosity=1).run(suite)
    else:
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
