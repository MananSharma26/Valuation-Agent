"""Fetch company financial data from WRDS (Compustat Global + I/B/E/S)."""

from __future__ import annotations
import pandas as pd
from valuation.data.api_client import CompanyData


class WRDSClient:
    """Client for WRDS database queries."""

    def __init__(self, username: str = "manan26"):
        self._username = username
        self._db = None

    def _connect(self):
        """Lazy connection to WRDS. Reads credentials from ~/.pgpass."""
        if self._db is None:
            import os
            import pathlib

            # Read password from .pgpass so WRDS doesn't prompt interactively
            pgpass = pathlib.Path.home() / ".pgpass"
            if pgpass.exists() and "PGPASSWORD" not in os.environ:
                for line in pgpass.read_text().strip().splitlines():
                    parts = line.split(":")
                    if len(parts) >= 5 and "wrds" in parts[0]:
                        os.environ["PGPASSWORD"] = parts[4]
                        break

            import wrds
            self._db = wrds.Connection(wrds_username=self._username)
        return self._db

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None

    def search_company(self, name: str, loc: str | None = None) -> pd.DataFrame:
        """Search for companies by name. Returns gvkey, conm, loc (sic via g_company)."""
        db = self._connect()
        query = '''
            SELECT DISTINCT gvkey, conm, loc
            FROM comp_global_daily.g_funda
            WHERE UPPER(conm) LIKE UPPER(%(name)s)
            AND datafmt=%(fmt)s AND indfmt=%(ind)s AND consol=%(con)s
        '''
        params = {'name': f'%{name}%', 'fmt': 'HIST_STD', 'ind': 'INDL', 'con': 'C'}
        if loc:
            query += ' AND loc=%(loc)s'
            params['loc'] = loc
        query += ' ORDER BY conm LIMIT 20'
        return db.raw_sql(query, params=params)

    def fetch_financials_global(self, gvkey: str) -> CompanyData | None:
        """Fetch financials from Compustat Global by gvkey."""
        db = self._connect()

        # Annual fundamentals
        funda = db.raw_sql('''
            SELECT gvkey, conm, fyear, datadate, curcd, loc,
                   revt, sale, oibdp, oiadp, nicon,
                   at, lt, ceq, dltt, dlc, che,
                   capx, dp, cshoi, act, lct,
                   invt, rect, ap, xint, txt
            FROM comp_global_daily.g_funda
            WHERE gvkey = %(gvkey)s
            AND datafmt=%(fmt)s AND indfmt=%(ind)s AND consol=%(con)s
            ORDER BY fyear DESC
            LIMIT 15
        ''', params={'gvkey': gvkey, 'fmt': 'HIST_STD', 'ind': 'INDL', 'con': 'C'})

        if funda.empty:
            return None

        # Get company info from most recent year
        latest = funda.iloc[0]

        # Get SIC code from company table
        company_info = db.raw_sql('''
            SELECT gvkey, conm, sic, gind, loc
            FROM comp_global_daily.g_company
            WHERE gvkey = %(gvkey)s
        ''', params={'gvkey': gvkey})

        sic_code = None
        if not company_info.empty:
            sic_code = str(company_info.iloc[0].get('sic', ''))

        # Map Compustat columns to standard names for income statement
        income_data = funda[['fyear', 'revt', 'sale', 'oibdp', 'oiadp', 'nicon', 'xint', 'txt']].copy()
        income_data.columns = ['Fiscal Year', 'Total Revenue', 'Net Sales', 'EBITDA',
                               'Operating Income', 'Net Income', 'Interest Expense', 'Tax Provision']
        income_data = income_data.set_index('Fiscal Year').sort_index()

        # Balance sheet
        balance_data = funda[['fyear', 'at', 'lt', 'ceq', 'dltt', 'dlc', 'che', 'act', 'lct', 'invt', 'rect', 'ap']].copy()
        balance_data.columns = ['Fiscal Year', 'Total Assets', 'Total Liabilities',
                                'Total Stockholders Equity', 'Long Term Debt', 'Current Debt',
                                'Cash And Cash Equivalents', 'Current Assets', 'Current Liabilities',
                                'Inventory', 'Accounts Receivable', 'Accounts Payable']
        balance_data = balance_data.set_index('Fiscal Year').sort_index()

        # Cash flow (derive from available data)
        cf_data = funda[['fyear', 'capx', 'dp']].copy()
        cf_data.columns = ['Fiscal Year', 'Capital Expenditure', 'Depreciation And Amortization']
        cf_data = cf_data.set_index('Fiscal Year').sort_index()

        # Country mapping
        loc_to_country = {
            'IND': 'India', 'USA': 'United States', 'GBR': 'United Kingdom',
            'JPN': 'Japan', 'CHN': 'China', 'DEU': 'Germany', 'FRA': 'France',
            'AUS': 'Australia', 'CAN': 'Canada', 'KOR': 'South Korea',
            'TWN': 'Taiwan', 'HKG': 'Hong Kong', 'SGP': 'Singapore',
            'BRA': 'Brazil', 'MEX': 'Mexico', 'ZAF': 'South Africa',
        }
        country = loc_to_country.get(str(latest.get('loc', '')), str(latest.get('loc', '')))

        shares = float(latest.get('cshoi', 0) or 0)

        return CompanyData(
            ticker=f"WRDS:{gvkey}",
            name=str(latest.get('conm', '')),
            sector=None,  # Compustat uses SIC, not sector names
            industry=None,
            sic_code=sic_code,
            country=country,
            income_statement=income_data,
            balance_sheet=balance_data,
            cash_flow=cf_data,
            shares_outstanding=shares,
            market_cap=0,  # Not in Compustat Global g_funda
            price=0,
            beta=None,
            dividend_per_share=0,
            book_value_per_share=float(latest.get('ceq', 0) or 0) / shares if shares > 0 else 0,
        )

    def fetch_ibes_estimates(self, ticker: str) -> pd.DataFrame | None:
        """Fetch analyst consensus estimates from I/B/E/S."""
        db = self._connect()
        result = db.raw_sql('''
            SELECT ticker, statpers, measure, fiscalp, fpi,
                   meanest, medest, highest, lowest, numest,
                   actual, stdev
            FROM tr_ibes.statsum_epsint
            WHERE ticker = %(ticker)s
            AND measure = %(measure)s
            AND fpi IN (%(fpi1)s, %(fpi2)s)
            ORDER BY statpers DESC
            LIMIT 20
        ''', params={'ticker': ticker, 'measure': 'EPS', 'fpi1': '1', 'fpi2': '2'})

        if result.empty:
            return None
        return result

    def search_ibes_ticker(self, company_name: str, country_code: str = 'INR') -> pd.DataFrame:
        """Search for I/B/E/S ticker by company name."""
        db = self._connect()
        return db.raw_sql('''
            SELECT DISTINCT ticker, cname, curcode
            FROM tr_ibes.statsum_epsint
            WHERE UPPER(cname) LIKE UPPER(%(name)s)
            AND curcode = %(cur)s
            LIMIT 10
        ''', params={'name': f'%{company_name}%', 'cur': country_code})
