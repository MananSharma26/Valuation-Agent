#!/bin/bash
BASE="https://pages.stern.nyu.edu/~adamodar/pc/datasets"
BASE2="https://pages.stern.nyu.edu/~adamodar/pc"
# Use DATA_DIR env var if set, otherwise default to damodaran_data/ relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="${DATA_DIR:-$SCRIPT_DIR/damodaran_data}"
TOTAL=0
FAIL=0

dl() {
  local url="$1"
  local dest="$2"
  local file=$(basename "$url")
  if wget -q -O "$dest/$file" "$url" 2>/dev/null; then
    TOTAL=$((TOTAL+1))
  else
    echo "FAILED: $url"
    FAIL=$((FAIL+1))
  fi
}

echo "=== Corporate Governance ==="
for f in inshold.xls insholdEurope.xls insholdJapan.xls insholdRest.xls insholdemerg.xls insholdChina.xls insholdIndia.xls insholdGlobal.xls; do
  dl "$BASE/$f" "$DIR/corporate_governance"
done

echo "=== Risk / Discount Rate ==="
# Historical Returns
dl "$BASE/histretSP.xls" "$DIR/risk_discount_rate"
# Implied ERP
dl "$BASE/histimpl.xls" "$DIR/risk_discount_rate"
# Country Risk Premiums
dl "$BASE/ctrypremApr26.xlsx" "$DIR/risk_discount_rate"
dl "$BASE/ctryprem.xlsx" "$DIR/risk_discount_rate"
dl "$BASE/ctrypremJuly25.xlsx" "$DIR/risk_discount_rate"
# Betas
for f in betas.xls betaEurope.xls betaJapan.xls betaRest.xls betaemerg.xls betaChina.xls betaIndia.xls betaGlobal.xls; do
  dl "$BASE/$f" "$DIR/risk_discount_rate"
done
# Country Tax Rates
dl "$BASE/countrytaxrates.xls" "$DIR/risk_discount_rate"
# Total Beta
for f in totalbeta.xls totalbetaEurope.xls totalbetaJapan.xls totalbetaRest.xls totalbetaemerg.xls totalbetaChina.xls totalbetaIndia.xls totalbetaGlobal.xls; do
  dl "$BASE/$f" "$DIR/risk_discount_rate"
done
# Market Cap Risk
dl "$BASE/mktcaprisk.xlsx" "$DIR/risk_discount_rate"
# WACC
for f in wacc.xls waccEurope.xls waccJapan.xls waccRest.xls waccemerg.xls waccChina.xls waccIndia.xls waccGlobal.xls; do
  dl "$BASE/$f" "$DIR/risk_discount_rate"
done
# Tax Rate by Industry
for f in taxrate.xls taxrateEurope.xls taxrateJapan.xls taxrateRest.xls taxrateemerg.xls taxrateChina.xls taxrateIndia.xls taxrateGlobal.xls; do
  dl "$BASE/$f" "$DIR/risk_discount_rate"
done

echo "=== Investment Returns ==="
# Dollar Value
for f in DollarUS.xls DollarEurope.xls DollarJapan.xls DollarRest.xls Dollaremerg.xls DollarChina.xls DollarIndia.xls DollarGlobal.xls; do
  dl "$BASE/$f" "$DIR/investment_returns"
done
# Market Cap
for f in MktCap.xls MktCapEurope.xls MktCapJapan.xls MktCapRest.xls MktCapemerg.xls MktCapChina.xls MktCapIndia.xls MktCapGlobal.xls; do
  dl "$BASE/$f" "$DIR/investment_returns"
done
# Employee
for f in Employee.xls EmployeeEurope.xls EmployeeJapan.xls EmployeeRest.xls Employeeemerg.xls EmployeeChina.xls EmployeeIndia.xls EmployeeGlobal.xls; do
  dl "$BASE/$f" "$DIR/investment_returns"
done
# EVA
for f in EVA.xls EVAEurope.xls EVAJapan.xls EVARest.xls EVAemerg.xls EVAChina.xls EVAIndia.xls EVAGlobal.xls; do
  dl "$BASE/$f" "$DIR/investment_returns"
done

echo "=== Capital Structure ==="
# Debt Details
for f in debtdetails.xls debtdetailsEurope.xls debtdetailsJapan.xls debtdetailsRest.xls debtdetailsemerg.xls debtdetailsChina.xls debtdetailsIndia.xls debtdetailsGlobal.xls; do
  dl "$BASE/$f" "$DIR/capital_structure"
done
# Debt Fund
for f in dbtfund.xls dbtfundEurope.xls dbtfundJapan.xls dbtfundRest.xls dbtfundemerg.xls dbtfundChina.xls dbtfundIndia.xls dbtfundGlobal.xls; do
  dl "$BASE/$f" "$DIR/capital_structure"
done
# Ratings
dl "$BASE2/ratings.xls" "$DIR/capital_structure"
# Lease Effect
for f in leaseeffect.xls leaseeffectEurope.xls leaseeffectJapan.xls leaseeffectRest.xls leaseeffectemerg.xls leaseeffectChina.xls leaseeffectIndia.xls leaseeffectGlobal.xls; do
  dl "$BASE/$f" "$DIR/capital_structure"
done
# Duration/Macro
dl "$BASE2/macrodur.xls" "$DIR/capital_structure"
dl "$BASE/macro.xls" "$DIR/capital_structure"

echo "=== Dividend Policy ==="
# Div vs FCFE
for f in divfcfe.xls divfcfeEurope.xls divfcfeJapan.xls divfcfeRest.xls divfcfeemerg.xls divfcfeChina.xls divfcfeIndia.xls divfcfeGlobal.xls; do
  dl "$BASE/$f" "$DIR/dividend_policy"
done
# Div Fund
for f in divfund.xls divfundEurope.xls divfundJapan.xls divfundRest.xls divfundemerg.xls divfundChina.xls divfundIndia.xls divfundGlobal.xls; do
  dl "$BASE/$f" "$DIR/dividend_policy"
done

echo "=== Cash Flow Estimation ==="
# CapEx
for f in capex.xls capexEurope.xls capexJapan.xls capexRest.xls capexemerg.xls capexChina.xls capexIndia.xls capexGlobal.xls; do
  dl "$BASE/$f" "$DIR/cash_flow_estimation"
done
# R&D
for f in "R&D.xls" "R&DEurope.xls" "R&DJapan.xls" "R&DRest.xls" "R&Demerg.xls" "R&DChina.xls" "R&DIndia.xls" "R&DGlobal.xls"; do
  dl "$BASE/$f" "$DIR/cash_flow_estimation"
done
# Goodwill
for f in goodwill.xls goodwillEurope.xls goodwillJapan.xls goodwillRest.xls goodwillemerg.xls goodwillChina.xls goodwillIndia.xls goodwillGlobal.xls; do
  dl "$BASE/$f" "$DIR/cash_flow_estimation"
done
# Margins
for f in margin.xls marginEurope.xls marginJapan.xls marginRest.xls marginemerg.xls marginChina.xls marginIndia.xls marginGlobal.xls; do
  dl "$BASE/$f" "$DIR/cash_flow_estimation"
done
# Fin Flows
for f in finflows.xls finflowsEurope.xls finflowsJapan.xls finflowsRest.xls finflowsemerg.xls finflowsChina.xls finflowsIndia.xls finflowsGlobal.xls; do
  dl "$BASE/$f" "$DIR/cash_flow_estimation"
done
# Working Capital
for f in wcdata.xls wcdataEurope.xls wcdataJapan.xls wcdataRest.xls wcdataemerg.xls wcdataChina.xls wcdataIndia.xls wcdataGlobal.xls; do
  dl "$BASE/$f" "$DIR/cash_flow_estimation"
done

echo "=== Growth Rate Estimation ==="
# ROE
for f in roe.xls roeEurope.xls roeJapan.xls roeRest.xls roeemerg.xls roeChina.xls roeIndia.xls roeGlobal.xls; do
  dl "$BASE/$f" "$DIR/growth_rate_estimation"
done
# Fundamental Growth EPS
for f in fundgr.xls fundgrEurope.xls fundgrJapan.xls fundgrRest.xls fundgremerg.xls fundgrChina.xls fundgrIndia.xls fundgrGlobal.xls; do
  dl "$BASE/$f" "$DIR/growth_rate_estimation"
done
# Historical Growth
for f in histgr.xls histgrEurope.xls histgrJapan.xls histgrRest.xls histgremerg.xls histgrChina.xls histgrIndia.xls histgrGlobal.xls; do
  dl "$BASE/$f" "$DIR/growth_rate_estimation"
done
# Fundamental Growth EBIT
for f in fundgrEB.xls fundgrEBEurope.xls fundgrEBJapan.xls fundgrEBRest.xls fundgrEBemerg.xls fundgrEBChina.xls fundgrEBIndia.xls fundgrEBGlobal.xls; do
  dl "$BASE/$f" "$DIR/growth_rate_estimation"
done

echo "=== Multiples ==="
# PE
for f in pedata.xls peEurope.xls peJapan.xls peRest.xls peemerg.xls peChina.xls peIndia.xls peGlobal.xls; do
  dl "$BASE/$f" "$DIR/multiples"
done
# PBV
for f in pbvdata.xls pbvEurope.xls pbvJapan.xls pbvRest.xls pbvemerg.xls pbvChina.xls pbvIndia.xls pbvGlobal.xls; do
  dl "$BASE/$f" "$DIR/multiples"
done
# PS
for f in psdata.xls psEurope.xls psJapan.xls psRest.xls psemerg.xls psChina.xls psIndia.xls psGlobal.xls; do
  dl "$BASE/$f" "$DIR/multiples"
done
# EV/EBITDA
for f in vebitda.xls vebitdaEurope.xls vebitdaJapan.xls vebitdaRest.xls vebitdaemerg.xls vebitdaChina.xls vebitdaIndia.xls vebitdaGlobal.xls; do
  dl "$BASE/$f" "$DIR/multiples"
done
# Market Cap Multiples
dl "$BASE/mktcapmult.xlsx" "$DIR/multiples"
# Country Stats
dl "$BASE/countrystats.xls" "$DIR/multiples"

echo "=== Option Pricing ==="
for f in optvar.xls optvarEurope.xls optvarJapan.xls optvarRest.xls optvaremerg.xls optvarChina.xls optvarIndia.xls optvarGlobal.xls; do
  dl "$BASE/$f" "$DIR/option_pricing"
done

echo ""
echo "========================================="
echo "Download complete: $TOTAL succeeded, $FAIL failed"
echo "========================================="
