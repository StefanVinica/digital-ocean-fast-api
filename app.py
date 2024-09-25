from fastapi import FastAPI, HTTPException
import requests

app = FastAPI()

@app.get("/property/{initial_id}")
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