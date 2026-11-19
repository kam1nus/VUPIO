import unittest
from scripts.link_readme_release import updated_readme

class ReleaseLinkTests(unittest.TestCase):
    def test_changes_downloads_without_rewriting_transition_instructions(self):
        original='## Download VUPIO Alpha 4059\n[Mac](https://github.com/kam1nus/VUPIO/releases/download/alpha-4059/app.pkg)\n\n## Updates\nInstall 4059 once.\n'
        actual=updated_readme(original,4060)
        self.assertIn('Alpha 4060',actual)
        self.assertIn('/alpha-4060/',actual)
        self.assertIn('Install 4059 once.',actual)
        self.assertEqual(updated_readme(actual,4059),actual)
        self.assertEqual(updated_readme(actual,4060),actual)
