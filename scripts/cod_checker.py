import requests
import os
import time
import argparse
import pandas as pd
from tqdm import tqdm

def run_cod_query(cod_id):
    """
    Fetches metadata for a single COD ID to get the DOI.
    """
    base_url = "https://www.crystallography.net/cod/result?"
    query = f"format=csv&id={cod_id}"
    url = base_url + query
    
    try:
        df = pd.read_csv(url, comment='#')
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    except Exception as e:
        print(f"Error fetching metadata for {cod_id}: {e}")
        return None

def download_cif(cod_id, output_dir):
    """
    Downloads the CIF file from COD.
    """
    cif_url = f"https://www.crystallography.net/cod/{cod_id}.cif"
    filepath = os.path.join(output_dir, f"{cod_id}.cif")
    
    try:
        response = requests.get(cif_url, timeout=30)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(response.content)
        return filepath
    except Exception as e:
        print(f"Error downloading CIF for {cod_id}: {e}")
        return None

def submit_to_checkcif(cif_path, cod_id, output_dir):
    """
    Submits a CIF file to the IUCr checkCIF service.
    """
    # Based on the form at https://checkcif.iucr.org/
    url = "https://checkcif.iucr.org/cgi-bin/checkcif_hkl.pl"
    
    data = {
        'validtype': 'checkcif_only',  # COD entries usually don't have HKL in the main CIF
        'outputtype': 'HTML',
        'valout': 'vrfno',
        'duplic': 'duplicno',
        'runtype': 'symmonly',
        'referer': 'checkcif_server',
        'from_index': 'from_index',
        'UPLOAD': 'Send CIF for checking'
    }
    
    try:
        with open(cif_path, 'rb') as f:
            files = {'filecif': (os.path.basename(cif_path), f, 'text/plain')}
            response = requests.post(url, data=data, files=files, timeout=60)
            response.raise_for_status()
            
            report_path = os.path.join(output_dir, f"checkcif_{cod_id}.html")
            with open(report_path, 'w', encoding='utf-8') as rf:
                rf.write(response.text)
            return report_path
    except Exception as e:
        print(f"Error submitting {cod_id} to checkCIF: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="COD Checker: Automate CIF download and checkCIF validation.")
    parser.add_argument("ids", nargs="*", help="List of COD IDs to process.")
    parser.add_argument("-f", "--file", help="Text file containing COD IDs (one per line).")
    parser.add_argument("-o", "--output", default="cod_checks", help="Output directory for reports and CIFs.")
    parser.add_argument("-d", "--delay", type=float, default=5.0, help="Delay in seconds between requests (default: 5.0).")
    
    args = parser.parse_args()
    
    cod_ids = args.ids
    if args.file:
        with open(args.file, 'r') as f:
            cod_ids.extend([line.strip() for line in f if line.strip()])
    
    if not cod_ids:
        print("No COD IDs provided. Use positional arguments or -f.")
        return

    os.makedirs(args.output, exist_ok=True)
    
    print(f"Starting processing for {len(cod_ids)} entries...")
    results = []

    for i, cod_id in enumerate(tqdm(cod_ids)):
        entry_data = {
            'cod_id': cod_id,
            'cif_status': 'Failed',
            'checkcif_status': 'Failed',
            'doi': 'N/A'
        }
        
        # 1. Fetch metadata (DOI)
        metadata = run_cod_query(cod_id)
        if metadata:
            entry_data['doi'] = metadata.get('doi', 'N/A')
        
        # 2. Download CIF
        cif_path = download_cif(cod_id, args.output)
        if cif_path:
            entry_data['cif_status'] = 'Downloaded'
            
            # 3. Submit to checkCIF
            report_path = submit_to_checkcif(cif_path, cod_id, args.output)
            if report_path:
                entry_data['checkcif_status'] = 'Success'
        
        results.append(entry_data)
        
        # Rate limiting
        if i < len(cod_ids) - 1:
            time.sleep(args.delay)

    # Save summary
    summary_df = pd.DataFrame(results)
    summary_path = os.path.join(args.output, "summary.csv")
    summary_df.to_csv(summary_path, index=False)
    
    print(f"\nProcessing complete!")
    print(f"Results saved to: {args.output}")
    print(f"Summary table: {summary_path}")
    print("\nSummary of results:")
    print(summary_df)

if __name__ == "__main__":
    main()
