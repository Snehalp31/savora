"""Print reproducible synthetic seed-data counts; MySQL population is a documented next integration step."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.reference_data import get_products,get_locations,get_partners,INVENTORY,SALES
if __name__=='__main__':
 print(json.dumps({'synthetic':True,'products':len(get_products()),'locations':len(get_locations()),'partners':len(get_partners()),'inventory_records':len(INVENTORY),'sales_records':len(SALES)},indent=2))
