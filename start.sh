#!/bin/bash
echo ""
echo " ================================================"
echo "  DataScope v2 - Analytics Job Radar"
echo "  Real jobs from Greenhouse, Lever, Ashby + more"
echo " ================================================"
echo ""

pip3 install flask requests beautifulsoup4 lxml python-dateutil --quiet 2>/dev/null || \
pip install flask requests beautifulsoup4 lxml python-dateutil --quiet

echo " Open your browser at: http://localhost:5000"
echo " Then click the green Scan Live Jobs button"
echo ""
python3 app.py 2>/dev/null || python app.py
