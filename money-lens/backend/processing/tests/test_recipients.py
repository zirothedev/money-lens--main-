from django.test import SimpleTestCase

from processing.recipients import clean_name, parse_description


class RecipientTests(SimpleTestCase):
    def parse(self, text, outgoing=True):
        return parse_description(text, outgoing)

    def test_outgoing_with_narration(self):
        p = self.parse('NIP TRANSFER TO AHMED MUSA/School fees/000013250903101500123456789')
        self.assertEqual((p.name, p.narration), ('AHMED MUSA', 'School fees'))

    def test_outgoing_without_narration(self):
        p = self.parse('TRF TO AHMED MUSA')
        self.assertEqual((p.name, p.narration), ('AHMED MUSA', ''))

    def test_reference_only_remainder_is_not_narration(self):
        p = self.parse('NIP TRANSFER TO AHMED MUSA/000013250903101500123456789')
        self.assertEqual((p.name, p.narration), ('AHMED MUSA', ''))

    def test_for_separator(self):
        p = self.parse('Transfer to Ahmed Musa for school fees')
        self.assertEqual((p.name, p.narration), ('Ahmed Musa', 'school fees'))

    def test_dash_separator(self):
        p = self.parse('Transfer to Ahmed Musa - Payment')
        self.assertEqual((p.name, p.narration), ('Ahmed Musa', 'Payment'))

    def test_incoming_uses_from(self):
        p = self.parse('NIP TRANSFER FROM GRACE OKAFOR FOR rent', outgoing=False)
        self.assertEqual((p.name, p.narration), ('GRACE OKAFOR', 'rent'))

    def test_direction_matters(self):
        self.assertIsNone(self.parse('TRANSFER TO AHMED MUSA', outgoing=False).name)
        self.assertIsNone(self.parse('TRANSFER FROM AHMED MUSA', outgoing=True).name)

    def test_unidentifiable_stays_none(self):
        for text in ['POS PURCHASE SHOPRITE', 'AIRTIME PURCHASE', 'ATM WITHDRAWAL', 'SMS ALERT FEE', '',
                     'TRANSFER TO 0123456789', 'TRANSFER TO ACCOUNT 0123456789', 'TRANSFER TO SELF']:
            p = self.parse(text)
            self.assertIsNone(p.name, text)
            self.assertEqual(p.narration, '', text)

    def test_name_with_punctuation(self):
        self.assertEqual(self.parse("TRF TO ANNE-MARIE O'BRIEN").name, "ANNE-MARIE O'BRIEN")

    def test_clean_name(self):
        self.assertEqual(clean_name('  Ahmed   Musa. '), 'Ahmed Musa')
        for bad in ['', None, '-', '12345', 'N/A', 'Unknown', 'A']:
            self.assertIsNone(clean_name(bad), bad)
