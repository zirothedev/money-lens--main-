"""Bank-specific description formats. All names below are fictional; the *shapes* are real GTBank/card-network text."""
from decimal import Decimal

from django.test import SimpleTestCase

from processing.formats import parse_known_format
from processing.normalizer import unify_spellings
from processing.recipients import parse_description
from processing.schema import NormalizedTransaction

NIP = 'Instant Payment Outward 000013260801112746000108527582 NIP TRANSFER TO {inst} - {name}'


def known(text, outgoing=True):
    return parse_known_format(text, outgoing)


class NipOutwardTests(SimpleTestCase):
    def test_name_after_the_dash_and_bank_kept_separately(self):
        r = known(NIP.format(inst='OPAY', name='ADA OBI'))
        self.assertEqual((r.name, r.via, r.narration), ('ADA OBI', 'OPAY', ''))

    def test_every_institution_style(self):
        for inst in ['MOMO', 'MONIEMFB', 'SMARTCASH', 'FCMB', 'KMB', 'PALMPAY', 'ZBN', 'FBN', 'PARALLEX']:
            r = known(NIP.format(inst=inst, name='ADA OBI'))
            self.assertEqual((r.name, r.via), ('ADA OBI', inst), inst)

    def test_outward_transfer_wording(self):
        r = known('Instant Payment Outward 000013260820150339000035116270 OUTWARD TRANSFER TO OPAY - ADA OBI')
        self.assertEqual((r.name, r.via, r.narration), ('ADA OBI', 'OPAY', ''))

    def test_note_written_before_the_transfer_becomes_narration(self):
        r = known('Instant Payment Outward 000013260909192109000082407401 ICE CREAM TO KMB - MARY OKON')
        self.assertEqual((r.name, r.via, r.narration), ('MARY OKON', 'KMB', 'ICE CREAM'))

    def test_note_written_after_the_bank(self):
        r = known(NIP.format(inst='MONIEMFB', name='POS TRANSFER- JANE ROE'))
        self.assertEqual((r.name, r.narration), ('JANE ROE', 'POS TRANSFER'))

    def test_names_with_commas_and_hyphens_are_kept(self):
        self.assertEqual(known(NIP.format(inst='KMB', name='OKON, MARY CHIDINMA')).name, 'OKON, MARY CHIDINMA')
        self.assertEqual(known(NIP.format(inst='OPAY', name="ANNE-MARIE O'BRIEN")).name, "ANNE-MARIE O'BRIEN")

    def test_a_service_named_in_the_statement_is_reported_as_written(self):
        self.assertEqual(known(NIP.format(inst='PARALLEX', name='NIBSS MANDATE ACTIVATION')).name, 'NIBSS MANDATE ACTIVATION')

    def test_wrapped_text_and_extra_spaces(self):
        r = known('Instant Payment Outward   000013260801112746000108527582\nNIP TRANSFER TO OPAY  -  ADA   OBI')
        self.assertEqual(r.name, 'ADA OBI')

    def test_only_outgoing(self):
        self.assertIsNone(known(NIP.format(inst='OPAY', name='ADA OBI'), outgoing=False))

    def test_other_banks_keep_the_generic_reading(self):
        """'TO <name> - <narration>' from another bank must NOT be read as '<bank> - <name>'."""
        p = parse_description('NIP TRANSFER TO JOHN DOE - PAYMENT FOR RENT', outgoing=True)
        self.assertEqual((p.name, p.narration, p.via), ('JOHN DOE', 'PAYMENT FOR RENT', ''))

    def test_gtbank_text_without_a_dash_falls_back_to_generic(self):
        p = parse_description('Instant Payment Outward 000013260801112746000108527582 NIP TRANSFER TO ADA OBI', True)
        self.assertEqual(p.name, 'ADA OBI')


class AirtimeAndDebitTests(SimpleTestCase):
    AIRTIME = ('Airtime Purchase VIA AIRTIME VIA GTWORLD 101CT0000000006422580686-2347044197672-{kind} '
               'FROM TEST , USER ONE TO {network} AIRTIME COLLECTION SALES')

    def test_airtime_networks(self):
        for network in ['MTN', 'AIRTEL', 'GLO']:
            r = known(self.AIRTIME.format(kind='AIRTIME', network=network))
            self.assertEqual(r.name, f'{network} AIRTIME COLLECTION SALES', network)

    def test_data_purchase(self):
        self.assertEqual(known(self.AIRTIME.format(kind='DATA', network='MTN')).name, 'MTN AIRTIME COLLECTION SALES')

    def test_airtime_without_a_beneficiary_stays_unnamed(self):
        self.assertIsNone(known('Airtime Purchase VIA AIRTIME VIA GTWORLD 101CT0000000006422580686'))

    def test_direct_debit_with_full_company_name(self):
        r = known('NIPS DIRECT DEBIT VIA NIP 999999260807063143115104549766NIPMINI/09056 72608070631431669776 81190/'
                  'MONDAVID IMOH TO MONO TECHNOLOGIES NIGERIA LTD FROM22377624 6559: - QUICKSAVE TO PIGGYBANK:FROM OBOT')
        self.assertEqual((r.name, r.narration), ('MONO TECHNOLOGIES NIGERIA LTD', 'QUICKSAVE TO PIGGYBANK:FROM OBOT'))

    def test_direct_debit_with_the_name_truncated_by_the_bank(self):
        r = known('NIPS DIRECT DEBIT VIA NIP 999999260802050341614248944559NIPMINI/09056 72608020503415504 51237897/'
                  'MONT:FROM OBOT DAVID IMOH TO MONO TECHNOLOGIES NIGER76389542 8231: - SCHEDULED PIGGYBANK AUTOSAVE DEBI')
        self.assertEqual((r.name, r.narration), ('MONO TECHNOLOGIES NIGER', 'SCHEDULED PIGGYBANK AUTOSAVE DEBI'))

    def test_gtworld_transfer_out_and_in(self):
        out = known('TRANSFER BETWEEN CUSTOMERS VIA GTWORLD OFFERING FROM TEST , USER ONE TO HOUSE ON THE ROCK-BAUCHI')
        self.assertEqual((out.name, out.narration), ('HOUSE ON THE ROCK-BAUCHI', 'OFFERING'))
        inc = known('TRANSFER BETWEEN CUSTOMERS VIA GTWORLD FOR LAPTOP FROM JANE ROE TO TEST , USER ONE', outgoing=False)
        self.assertEqual((inc.name, inc.narration), ('JANE ROE', 'LAPTOP'))


class CardMerchantTests(SimpleTestCase):
    def name(self, text):
        r = known(text)
        return r.name if r else None

    def test_pos_withdrawal_agent_with_random_code_and_terminal(self):
        self.assertEqual(self.name('Cash withdrawal by Self via POS POS PUR T JANE ROE FiZOFB 20338BOD LANG 296960 '
                                   '260801FiZOFB 20338BOD539983*********6603'), 'JANE ROE')

    def test_city_glued_onto_a_full_width_name_is_removed_but_the_truncated_name_is_kept_as_written(self):
        self.assertEqual(self.name('POSWEB PURCHASE TRANSACTION POS PUR OPAY KURE BUSINESS ENTEBauchi BANG 857546 '
                                   '001776099175 4001LUJW539983*********6603'), 'OPAY KURE BUSINESS ENTE')
        self.assertEqual(self.name('POSWEB PURCHASE TRANSACTION POS PUR OPAY SAMSON OLUSHOLA OMBauchi Capi BANG 005520 '
                                   '609092235819 257ZTSWS539983*********6603'), 'OPAY SAMSON OLUSHOLA OM')
        self.assertEqual(self.name('POSWEB PURCHASE TRANSACTION POS PUR OPAY Aplus identificatiOther BANG 003706 '
                                   '609029867504 257ZALOL539983*********6603'), 'OPAY Aplus identificati')

    def test_uppercase_city_glued_on(self):
        self.assertEqual(self.name('Cash withdrawal by Self via POS POS WD ALSAM GENERAL ENTERPRISLAGOS LANG 836926 '
                                   '109994816768 2TPT0QJP539983*********6603'), 'ALSAM GENERAL ENTERPRIS')

    def test_city_as_a_separate_trailing_word(self):
        for tail, expected in [('ADAH JOHN ANDREW LAGOS LANG', 'ADAH JOHN ANDREW'), ('PALMPAY LIMITED LA LANG', 'PALMPAY LIMITED'),
                               ('IDRIS PHOEBE SALEH Bauchi NG', 'IDRIS PHOEBE SALEH')]:
            text = f'POSWEB PURCHASE TRANSACTION POS PUR {tail} 019770 672898366912 221491VR539983*********6603'
            self.assertEqual(self.name(text), expected, tail)

    def test_t_format_in_a_purchase(self):
        self.assertEqual(self.name('POSWEB PURCHASE TRANSACTION POS PUR T SOPHIA AGBO DDBXYG 2070SJP9 LANG 090670 '
                                   '001817317516 2070SJP9539983*********6603'), 'SOPHIA AGBO')

    def test_names_are_kept_exactly_as_written(self):
        self.assertEqual(self.name('Cash withdrawal by Self via POS POS PUR T Al sam general en Ihhehi 2033V5MC LANG 206400 '
                                   '260817Ihhehi 2033V5MC539983*********6603'), 'Al sam general en')

    def test_a_name_that_merely_starts_with_t_is_not_mistaken_for_the_terminal_flag(self):
        self.assertEqual(self.name('Cash withdrawal by Self via POS POS PUR TOGETHERNESS DV V knz8IB 2TMP3NYN LANG 549760 '
                                   '260815knz8IB 2TMP3NYN539983*********6603'), 'TOGETHERNESS DV V')

    def test_web_purchase_reports_the_merchant_id_and_name(self):
        r = known('POSWEB PURCHASE TRANSACTION WEB PUR 3PG00001 PIGG Y EST LANG 398973 GIPS MRA4FY 3PG00001539983*********6603')
        self.assertEqual((r.name, r.merchant_id), ('PIGG Y EST', '3PG00001'))

    def test_web_purchase_without_a_clean_id_is_still_named(self):
        r = known('POSWEB PURCHASE TRANSACTION WEB PUR PiggyV t6464650640i10000 LANG 450262 168883450262 3IPG0001539983*********6603')
        self.assertEqual((r.name, r.merchant_id), ('PiggyV t6464650640i10000', ''))

    def test_card_text_only_for_outgoing(self):
        self.assertIsNone(known('POSWEB PURCHASE TRANSACTION POS PUR OPAY KURE BUSINESS ENTEBauchi BANG 857546 '
                                '001776099175 4001LUJW539983*********6603', outgoing=False))

    def test_unrecognised_descriptions_are_not_guessed(self):
        for text in ['SMS ALERT FEE', 'VAT ON CHARGES', 'ATM WITHDRAWAL', 'POS PURCHASE SHOPRITE ABUJA', '']:
            self.assertIsNone(known(text), text)


def tx(recipient, merchant_id='', day=1):
    from datetime import date
    return NormalizedTransaction(date=date(2026, 8, day), description='x', debit=Decimal('50'), credit=None,
                                 recipient=recipient, merchant_id=merchant_id)


class UnifySpellingsTests(SimpleTestCase):
    def test_variants_with_the_same_merchant_id_take_the_most_common_spelling(self):
        out = unify_spellings([tx('PIGG Y EST', 'A1'), tx('PI GG VEST', 'A1'), tx('PIGG Y EST', 'A1'), tx('P I GYVEST', 'A1')])
        self.assertEqual({t.recipient for t in out}, {'PIGG Y EST'})

    def test_a_tie_goes_to_the_earliest_spelling(self):
        out = unify_spellings([tx('PI GG VEST', 'A1'), tx('PIGG Y EST', 'A1')])
        self.assertEqual({t.recipient for t in out}, {'PI GG VEST'})

    def test_different_ids_and_missing_ids_are_never_merged(self):
        out = unify_spellings([tx('PIGG Y EST', 'A1'), tx('PI GG VEST', 'B2'), tx('PIGGV EST', ''), tx('PIGGV EST', '')])
        self.assertEqual([t.recipient for t in out], ['PIGG Y EST', 'PI GG VEST', 'PIGGV EST', 'PIGGV EST'])

    def test_unnamed_transactions_stay_unnamed(self):
        out = unify_spellings([tx('PIGG Y EST', 'A1'), tx(None, 'A1')])
        self.assertIsNone(out[1].recipient)


class MoniepointFormatTests(SimpleTestCase):
    def mp(self, text, hint='', outgoing=True):
        return parse_known_format(text, outgoing, hint)

    def test_transfer_to_splits_the_name_from_the_bank_using_the_institution_cell(self):
        r = self.mp('TRANSFER TO ADA OBI OPay *****41388 /TRF|2MPT|20946', 'OPay')
        self.assertEqual((r.name, r.via), ('ADA OBI', 'OPay'))
        r = self.mp('TRANSFER TO ADA OBI Guaranty Trust Bank *****54059/TRF|2MPT', 'Guaranty Trust Bank')
        self.assertEqual((r.name, r.via), ('ADA OBI', 'Guaranty Trust Bank'))

    def test_a_name_that_overflowed_into_the_institution_cell_still_splits_correctly(self):
        r = self.mp('TRANSFER TO MUHAMMAD AHMAD EL-KUFAHN Jaiz Bank *****57206/TRF|2MPT', 'NJaiz Bank')
        self.assertEqual((r.name, r.via), ('MUHAMMAD AHMAD EL-KUFAHN', 'Jaiz Bank'))

    def test_without_an_institution_it_does_not_guess_the_split(self):
        self.assertIsNone(self.mp('TRANSFER TO ADA OBI OPay *****41388 /TRF|2MPT', ''))

    def test_pos_transfer_variants(self):
        for body in ['POS Transfer- ADA OBI', 'POS Transfer-ADA OBI', 'POS Transfer - ADA OBI']:
            r = self.mp(f'TRANSFER TO {body} Moniepoint MFB *****54528/TRF|2MPT', 'Moniepoint MFB')
            self.assertEqual((r.name, r.narration), ('ADA OBI', 'POS Transfer'), body)

    def test_internal_transfers_out_and_in(self):
        out = self.mp('TEST USER ONE TO JOHN ROE MONIEPOINT *****94601/TRF|2MPT_CBA', 'Moniepoint MFB')
        self.assertEqual((out.name, out.via), ('JOHN ROE', 'Moniepoint MFB'))
        inc = self.mp('YASIR HALADU AUWAL TO TEST USER ONE MONIEPOINT *****23949/TRF|2MPT_CBA', outgoing=False)
        self.assertEqual(inc.name, 'YASIR HALADU AUWAL')

    def test_pos_purchase_merchant_flag_and_counter(self):
        cases = {'POS purchase at T ABDUL BOSS BUSINE 000': 'ABDUL BOSS BUSINE', 'POS purchase at OPAY DIGITAL SERVICES L': 'OPAY DIGITAL SERVICES L',
                 'POS purchase at T A I ZIRA OIL AND 016': 'A I ZIRA OIL AND', 'POS purchase at T nasiru danbaba 002': 'nasiru danbaba',
                 'POS purchase at PALMPAY LIMITED': 'PALMPAY LIMITED', 'POS purchase at TOGETHERNESS STORES': 'TOGETHERNESS STORES'}
        for text, expected in cases.items():
            self.assertEqual(self.mp(text).name, expected, text)

    def test_airtime_bill_payment_and_labelled_fees(self):
        self.assertEqual(self.mp('AIRTIME TO 09032344047 MTN /ATP|2MPT|2092').name, '09032344047 MTN')
        self.assertEqual(self.mp('BILL PAYMENT FOR FIDELIS EMEREMGINI 4 Jos Electricity Distribution Prepaid 45160735572 /BPT|2MPT',
                                 'Jos Electricity Distribution Prepaid').name, 'Jos Electricity Distribution Prepaid')
        self.assertIsNone(self.mp('BILL PAYMENT FOR X 4 Some Biller 45160735572 /BPT|2MPT', ''))
        for label in ['Stamp duty', 'Value Added Tax']:
            self.assertEqual(self.mp(label).name, label)
        self.assertEqual(self.mp('CARD REQUEST AND DELIVERY|ECR|CS|5311023949|7459980972').name, 'CARD REQUEST AND DELIVERY')

    def test_unrelated_text_and_credits_are_left_alone(self):
        self.assertIsNone(self.mp('Transfer from ALIYU ALI MUSA', outgoing=False))
        self.assertIsNone(self.mp('Transportation'))
        self.assertIsNone(self.mp('POS purchase at T SHOP 001', outgoing=False))
