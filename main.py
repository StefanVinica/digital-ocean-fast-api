from fastapi import APIRouter, HTTPException, Query
import csv
import requests
from fastapi.responses import StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
import io
from datetime import datetime
from urllib.parse import quote
from playwright.async_api import async_playwright

router = APIRouter()

# Initialize the Jinja2 environment
env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape(['html', 'xml'])
)

# Add a custom filter to format datetime
def datetimeformat(value, format='%Y-%m-%d'):
    return datetime.fromtimestamp(value / 1000).strftime(format)

def format_sales_date(timestamp):
    if timestamp:
        # Assuming timestamp is in milliseconds
        return datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d')
    return ''

env.filters['datetimeformat'] = datetimeformat

@router.get("/property/{initial_id}")
async def get_property(initial_id: int):
    """
    Fetch the source property and selected comparable properties based on initial_id.
    """
    # Step 1: Fetch the source property data
    source_property_url = f'https://xano.anant.systems/api:gqF_nDUq/ripos/valuations_property/{initial_id}'
    
    try:
        source_response = requests.get(source_property_url)
        source_response.raise_for_status()
        source_property = source_response.json()
    except requests.exceptions.HTTPError:
        raise HTTPException(status_code=source_response.status_code, detail="Source property not found.")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="An error occurred while fetching the source property.")
    
    # Step 2: Fetch all property comparisons
    comparisons_url = 'https://xano.anant.systems/api:rhC7uFD7/ripos/valuations_property_comparisons'
    
    try:
        comparisons_response = requests.get(comparisons_url)
        comparisons_response.raise_for_status()
        comparisons_data = comparisons_response.json()
    except requests.exceptions.HTTPError:
        raise HTTPException(status_code=comparisons_response.status_code, detail="Failed to fetch property comparisons.")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="An error occurred while fetching property comparisons.")
    
    # Step 3: Filter the property comparisons
    filtered_comparisons = []
    for comparison in comparisons_data:
        # Retrieve initial_id and Selected from the comparison
        comparison_initial_id = comparison.get('initial_id')
        selected = comparison.get('Selected')
        
        # Ensure initial_id is an integer
        try:
            comparison_initial_id = int(comparison_initial_id)
        except (ValueError, TypeError):
            continue  # Skip if initial_id is invalid
        
        # Check if initial_id matches and Selected is True
        if comparison_initial_id == initial_id and selected == True:
            filtered_comparisons.append(comparison)
    
    # Step 4: Create the response
    result = {
        'source_property': source_property,
        'selected_comparisons': filtered_comparisons
    }
    
    return result

@router.get("/property/{initial_id}/report", response_class=StreamingResponse)
async def generate_report(initial_id: int):
    result = await get_property(initial_id)

    # Render the HTML template with data
    template = env.get_template('report.html')
    html_content = template.render(
        source_property=result['source_property'],
        selected_comparisons=result['selected_comparisons']
    )

    # Generate PDF using Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_content, wait_until='networkidle')
        pdf_bytes = await page.pdf()
        await browser.close()

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=property_report_{initial_id}.pdf"
        }
    )
    
@router.get("/property/report/csv")
async def generate_csv_report(user_email: str = Query(...), report_id: int = Query(...)):
    """
    Generate a CSV report for a specific user's report containing selected comparable properties.
    """
    # Fetch all user reports
    user_reports_response = requests.get("https://xano.anant.systems/api:BKZAQvfA/ripos_valuations_user_reports")
    if user_reports_response.status_code != 200:
        raise HTTPException(status_code=user_reports_response.status_code, detail="Failed to fetch user reports.")
    user_reports = user_reports_response.json()

    # Find the report matching user_email and report_id
    selected_report = next(
        (report for report in user_reports if report['id'] == report_id and report['user_id'] == user_email),
        None
    )

    if not selected_report:
        raise HTTPException(status_code=404, detail="User report not found.")

    # Get the property_ids from the report
    property_ids = selected_report.get('property_ids', [])
    if not property_ids:
        raise HTTPException(status_code=404, detail="No property IDs found in the user report.")

    # Fetch all comparable properties
    comparisons_response = requests.get("https://xano.anant.systems/api:rhC7uFD7/ripos/valuations_property_comparisons")
    if comparisons_response.status_code != 200:
        raise HTTPException(status_code=comparisons_response.status_code, detail="Failed to fetch property comparisons.")
    all_comparisons = comparisons_response.json()

    # Create a mapping from comparison id to comparison data
    comparisons_by_id = {comp['id']: comp for comp in all_comparisons}

    # Filter the comparisons to only include those in property_ids
    selected_comparisons_list = [comparisons_by_id[comp_id] for comp_id in property_ids if comp_id in comparisons_by_id]

    if not selected_comparisons_list:
        raise HTTPException(status_code=404, detail="No matching comparisons found for the given property IDs.")

    # Group selected comparisons by their initial_address (source property address)
    comparisons_by_initial_address = {}
    for comp in selected_comparisons_list:
        initial_address = comp.get('initial_address')
        if initial_address:
            comparisons_by_initial_address.setdefault(initial_address, []).append(comp)

    # Fetch all source properties
    properties_response = requests.get("https://xano.anant.systems/api:gqF_nDUq/ripos/valuations_property")
    if properties_response.status_code != 200:
        raise HTTPException(status_code=properties_response.status_code, detail="Failed to fetch properties.")
    source_properties = properties_response.json()

    # Create a mapping from address to source property
    source_properties_by_address = {prop['address']: prop for prop in source_properties}

    # Prepare CSV headers
    headers = [
        'Formula (Average of Comparables Sale Price(s))',
        'Source Property Address',
        'Source Bedrooms',
        'Source Bathrooms',
        'Source Square Feet',
        'Source Appraisal',
    ]

    # Determine the maximum number of comparisons among properties with selected comparisons
    max_comparisons = max(len(comparisons) for comparisons in comparisons_by_initial_address.values()) if comparisons_by_initial_address else 0

    # Add headers for comparisons
    for i in range(1, max_comparisons + 1):
        headers.extend([
            f'#{i}Comp Property Address',
            f'#{i}Comp Property Sale Date',
            f'#{i}Comp Bedrooms',
            f'#{i}Comp Bathrooms',
            f'#{i}Comp Square Feet',
            f'#{i}Comp Most Recent Sale Amount',
            f'#{i}Comp Redfin URL',
        ])

    # Create a CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    # Process each initial_address (source property)
    for initial_address, selected_comparisons in comparisons_by_initial_address.items():
        # Get the source property
        source_property = source_properties_by_address.get(initial_address)
        if not source_property:
            continue  # Skip if source property not found

        # Calculate average sold amount
        sold_amounts = [
            comp['sold_amount'] for comp in selected_comparisons if comp.get('sold_amount')
        ]
        average_sold_amount = sum(sold_amounts) / len(sold_amounts) if sold_amounts else 0

        # Prepare data row
        data_row = [
            average_sold_amount,
            initial_address,
            source_property.get('bedrooms', ''),
            source_property.get('bath', ''),
            source_property.get('square_feet', ''),
            source_property.get('appraisal_value', ''),
        ]

        # Add data for each comparison up to max_comparisons
        for comp in selected_comparisons:
            data_row.extend([
                comp.get('address', ''),
                format_sales_date(comp.get('sales_date')),
                comp.get('bedrooms', ''),
                comp.get('bath', ''),
                comp.get('floor_size_value', ''),
                comp.get('sold_amount', ''),
                comp.get('most_recent_url', ''),
            ])

        # If a property has fewer comparisons than max_comparisons, fill the rest with empty strings
        comparisons_filled = len(selected_comparisons)
        while comparisons_filled < max_comparisons:
            data_row.extend([''] * 7)  # 7 empty fields per comparison
            comparisons_filled += 1

        # Write the data row to CSV
        writer.writerow(data_row)

    output.seek(0)

    # Sanitize email by replacing "@" and "." to avoid issues with file names
    safe_email = user_email.replace('@', '_').replace('.', '_')

    # Generate the filename
    filename = f"property_report_{safe_email}_{report_id}.csv"

    return StreamingResponse(
        output,
        media_type='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="{quote(filename)}"'
        }
    )