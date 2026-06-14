"""Fetch company financial data from WRDS (Compustat Global + I/B/E/S)."""

from __future__ import annotations
import pandas as pd
from valuation.data.api_client import CompanyData


class WRDSClient:
    """Client for WRDS database queries."""

    def __init__(self, username: str = ""):
        self._username = username
        self._db = None

    def _connect(self):
        """Lazy connection to WRDS via direct sqlalchemy (no wrds library prompts)."""
        if self._db is None:
            import os
            import pathlib
            import sqlalchemy

            # Read credentials from .pgpass
            password = None
            pgpass = pathlib.Path.home() / ".pgpass"
            if pgpass.exists():
                for line in pgpass.read_text().strip().splitlines():
                    parts = line.split(":")
                    if len(parts) >= 5 and "wrds" in parts[0]:
                        self._username = parts[3]
                        password = parts[4]
                        break

            if not password:
                raise ConnectionError("No WRDS credentials found in ~/.pgpass")

            from urllib.parse import quote_plus
            engine = sqlalchemy.create_engine(
                f"postgresql://{self._username}:{quote_plus(password)}@wrds-pgdata.wharton.upenn.edu:9737/wrds",
                connect_args={"connect_timeout": 15},
            )
            self._db = engine.connect()
        return self._db

    def raw_sql(self, query: str, params: dict | None = None) -> pd.DataFrame:
        """Execute SQL and return DataFrame. Drop-in replacement for wrds.Connection.raw_sql.

        Converts %(name)s style params (used by wrds library / psycopg2)
        to :name style (used by sqlalchemy.text).
        Rolls back on error to prevent poisoned transaction state.
        """
        import re
        import sqlalchemy

        conn = self._connect()

        # Convert %(name)s → :name for sqlalchemy.text()
        converted_query = re.sub(r'%\((\w+)\)s', r':\1', query)

        try:
            return pd.read_sql(sqlalchemy.text(converted_query), conn, params=params)
        except Exception:
            # Rollback to clear failed transaction state
            try:
                conn.rollback()
            except Exception:
                pass
            raise

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
        return self.raw_sql(query, params=params)

    def fetch_financials_global(self, gvkey: str) -> CompanyData | None:
        """Fetch financials from Compustat Global by gvkey."""
        db = self._connect()

        # Annual fundamentals
        funda = self.raw_sql('''
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
        company_info = self.raw_sql('''
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

    def _ibes_table(self, region: str = "int") -> str:
        """Return correct I/B/E/S table name: _epsus for US, _epsint for international."""
        return f"tr_ibes.statsum_eps{'us' if region == 'us' else 'int'}"

    def fetch_ibes_estimates(self, ticker: str, region: str = "int") -> pd.DataFrame | None:
        """Fetch analyst consensus estimates from I/B/E/S.

        Args:
            ticker: I/B/E/S ticker (e.g., 'NVDA' for US, '@V9T' for TCS India)
            region: 'us' for US stocks, 'int' for international
        """
        db = self._connect()
        table = self._ibes_table(region)
        result = self.raw_sql(f'''
            SELECT ticker, statpers, measure, fiscalp, fpi,
                   meanest, medest, highest, lowest, numest,
                   actual, stdev
            FROM {table}
            WHERE ticker = %(ticker)s
            AND measure = %(measure)s
            AND fpi IN (%(fpi1)s, %(fpi2)s)
            ORDER BY statpers DESC
            LIMIT 20
        ''', params={'ticker': ticker, 'measure': 'EPS', 'fpi1': '1', 'fpi2': '2'})

        if result.empty:
            return None
        return result

    def fetch_top_analysts(self, ticker: str, region: str = "us", top_n: int = 10) -> pd.DataFrame | None:
        """Fetch accuracy-ranked analysts with their latest targets and recommendations.

        Accuracy = 1 - avg(|estimate - actual| / |actual|) over recent fiscal periods.
        Only includes analysts with 2+ estimates that have actuals.

        Args:
            ticker: I/B/E/S ticker (e.g., 'NVDA' for US, '@V9T' for TCS)
            region: 'us' for US stocks, 'int' for international
            top_n: Number of top analysts to return

        Returns:
            DataFrame with columns: analyst_name, firm, accuracy_pct, target,
            recommendation, num_estimates, latest_date
            Returns None if no data found or query fails.
        """
        db = self._connect()
        det_table = "tr_ibes.det_epsus" if region == "us" else "tr_ibes.det_epsint"

        # Step 1: Compute per-analyst average absolute percentage error
        # Only use estimates that have an actual value and are from 2022 onward
        try:
            accuracy_df = self.raw_sql(f"""
                SELECT
                    analys,
                    COUNT(*) AS num_estimates,
                    AVG(ABS(value - actual) / NULLIF(ABS(actual), 0)) AS avg_error,
                    MAX(anndats) AS latest_date
                FROM {det_table}
                WHERE ticker = %(ticker)s
                  AND actual IS NOT NULL
                  AND value IS NOT NULL
                  AND ABS(actual) > 0
                  AND anndats >= '2022-01-01'
                GROUP BY analys
                HAVING COUNT(*) >= 2
                ORDER BY avg_error ASC
                LIMIT %(limit)s
            """, params={"ticker": ticker, "limit": top_n * 3})
        except Exception:
            return None

        if accuracy_df is None or accuracy_df.empty:
            return None

        analyst_ids = accuracy_df["analys"].tolist()

        # Step 2: Get analyst names and firm codes from ptgdet (most recent per analyst)
        # amaskcd in ptgdet matches analys in det_epsus
        try:
            names_df = self.raw_sql("""
                SELECT DISTINCT ON (amaskcd)
                    amaskcd,
                    alysnam,
                    estimid
                FROM tr_ibes.ptgdet
                WHERE ticker = %(ticker)s
                  AND amaskcd IN :ids
                ORDER BY amaskcd, revdats DESC, revtims DESC
            """, params={"ticker": ticker, "ids": tuple(analyst_ids)})
        except Exception:
            names_df = pd.DataFrame(columns=["amaskcd", "alysnam", "estimid"])

        # Step 3: Get latest price target per analyst from ptgdet
        try:
            targets_df = self.raw_sql("""
                SELECT DISTINCT ON (amaskcd)
                    amaskcd,
                    horizon,
                    value AS target
                FROM tr_ibes.ptgdet
                WHERE ticker = %(ticker)s
                  AND amaskcd IN :ids
                  AND value IS NOT NULL
                ORDER BY amaskcd, revdats DESC, revtims DESC
            """, params={"ticker": ticker, "ids": tuple(analyst_ids)})
        except Exception:
            targets_df = pd.DataFrame(columns=["amaskcd", "target"])

        # Step 4: Get latest recommendation per analyst from recddet
        try:
            recs_df = self.raw_sql("""
                SELECT DISTINCT ON (amaskcd)
                    amaskcd,
                    irec
                FROM tr_ibes.recddet
                WHERE ticker = %(ticker)s
                  AND amaskcd IN :ids
                ORDER BY amaskcd, revdats DESC, revtims DESC
            """, params={"ticker": ticker, "ids": tuple(analyst_ids)})
        except Exception:
            recs_df = pd.DataFrame(columns=["amaskcd", "irec"])

        # Recommendation code mapping (I/B/E/S IREC coding)
        irec_map = {1: "STRONG BUY", 2: "BUY", 3: "HOLD", 4: "SELL", 5: "STRONG SELL"}

        # Step 5: Assemble final DataFrame
        results = []
        for _, acc_row in accuracy_df.iterrows():
            analyst_id = acc_row["analys"]
            avg_err = acc_row["avg_error"]
            num_est = int(acc_row["num_estimates"])
            latest = acc_row["latest_date"]

            # Accuracy as percentage (100% = perfect)
            accuracy_pct = max(0.0, (1.0 - float(avg_err)) * 100) if avg_err is not None else None

            # Name and firm
            analyst_name = None
            firm = None
            if names_df is not None and not names_df.empty:
                nm = names_df[names_df["amaskcd"] == analyst_id]
                if not nm.empty:
                    analyst_name = nm.iloc[0].get("alysnam")
                    firm = nm.iloc[0].get("estimid")

            # Target price
            target = None
            if targets_df is not None and not targets_df.empty:
                tgt = targets_df[targets_df["amaskcd"] == analyst_id]
                if not tgt.empty:
                    target = tgt.iloc[0].get("target")

            # Recommendation
            recommendation = None
            if recs_df is not None and not recs_df.empty:
                rec = recs_df[recs_df["amaskcd"] == analyst_id]
                if not rec.empty:
                    irec_val = rec.iloc[0].get("irec")
                    if irec_val is not None:
                        try:
                            recommendation = irec_map.get(int(irec_val), str(irec_val))
                        except (ValueError, TypeError):
                            recommendation = str(irec_val)

            results.append({
                "analyst_name": analyst_name if analyst_name else f"Analyst {analyst_id}",
                "firm": firm if firm else "N/A",
                "accuracy_pct": round(accuracy_pct, 1) if accuracy_pct is not None else None,
                "target": float(target) if target is not None else None,
                "recommendation": recommendation if recommendation else "N/A",
                "num_estimates": num_est,
                "latest_date": str(latest) if latest is not None else None,
            })

            if len(results) >= top_n:
                break

        if not results:
            return None

        return pd.DataFrame(results)

    def fetch_earnings_transcript(self, company_name: str, max_chars: int = 15000) -> dict | None:
        """Fetch the most recent earnings call transcript from Capital IQ via WRDS.

        Args:
            company_name: Company name to search for (e.g., "NVIDIA", "Tata Consultancy")
            max_chars: Max characters of transcript to return (truncate for LLM context window)

        Returns dict with: headline, date, transcript_text, num_components
        Returns None if not found.
        """
        db = self._connect()
        try:
            # Find most recent earnings call
            result = self.raw_sql('''
                SELECT transcriptid, companyname, headline, mostimportantdateutc
                FROM ciq_transcripts.wrds_transcript_detail
                WHERE UPPER(companyname) LIKE UPPER(%(name)s)
                AND keydeveventtypename = %(type)s
                ORDER BY mostimportantdateutc DESC
                LIMIT 1
            ''', params={'name': f'%{company_name}%', 'type': 'Earnings Calls'})

            if result.empty:
                return None

            tid = int(result.iloc[0]['transcriptid'])

            # Get transcript text
            text_df = self.raw_sql('''
                SELECT componentorder, componenttext
                FROM ciq_transcripts.ciqtranscriptcomponent
                WHERE transcriptid = %(tid)s
                ORDER BY componentorder
            ''', params={'tid': tid})

            if text_df.empty:
                return None

            full_text = ' '.join(text_df['componenttext'].astype(str).tolist())

            # Truncate for LLM context
            if len(full_text) > max_chars:
                full_text = full_text[:max_chars] + "\n\n[Transcript truncated...]"

            return {
                "headline": str(result.iloc[0]['headline']),
                "date": str(result.iloc[0]['mostimportantdateutc']),
                "company": str(result.iloc[0]['companyname']),
                "transcript_text": full_text,
                "num_components": len(text_df),
            }
        except Exception as e:
            print(f"  Transcript fetch error: {e}")
            return None

    def search_ibes_ticker(self, company_name: str, country_code: str = 'INR') -> pd.DataFrame:
        """Search for I/B/E/S ticker by company name.

        Searches both US and international tables.
        For US (country_code='USD'), searches statsum_epsus.
        For others, searches statsum_epsint.
        """
        db = self._connect()
        is_us = country_code == "USD"

        if is_us:
            # US table doesn't have curcode — search by name or ticker directly
            result = self.raw_sql('''
                SELECT DISTINCT ticker, cname, 'USD' as curcode
                FROM tr_ibes.statsum_epsus
                WHERE UPPER(cname) LIKE UPPER(%(name)s)
                LIMIT 10
            ''', params={'name': f'%{company_name}%'})
            # Also try exact ticker match
            if result.empty:
                result = self.raw_sql('''
                    SELECT DISTINCT ticker, cname, 'USD' as curcode
                    FROM tr_ibes.statsum_epsus
                    WHERE ticker = %(ticker)s
                    LIMIT 5
                ''', params={'ticker': company_name.upper()})
        else:
            result = self.raw_sql('''
                SELECT DISTINCT ticker, cname, curcode
                FROM tr_ibes.statsum_epsint
                WHERE UPPER(cname) LIKE UPPER(%(name)s)
                AND curcode = %(cur)s
                LIMIT 10
            ''', params={'name': f'%{company_name}%', 'cur': country_code})

        return result
