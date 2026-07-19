import os
import sys
import time
import subprocess

def run_pipeline(scans_dir, output_format="3mf", engine="local"):
    if engine == "api":
        print(f"Uploading datasets to External Free API (MOCK)...")
        time.sleep(2)
        print("Waiting for API processing...")
    elif engine == "cloud":
        print(f"Uploading datasets to Probharath Cloud (MOCK)...")
        time.sleep(2)
        print("Processing on cluster...")
    elif engine == "colmap":
        import shutil
        if not shutil.which("colmap"):
            print("Error: COLMAP is not installed. Please open a terminal and run 'brew install colmap'")
            sys.exit(1)
        
        print(f"Starting Probharath Engine (COLMAP Open Source) on directory: {scans_dir}")
        output_file = os.path.join(scans_dir, f"reconstructed_model.{output_format}")
        
        # Setup colmap workspace
        db_path = os.path.join(scans_dir, "database.db")
        sparse_dir = os.path.join(scans_dir, "sparse")
        dense_dir = os.path.join(scans_dir, "dense")
        os.makedirs(sparse_dir, exist_ok=True)
        os.makedirs(dense_dir, exist_ok=True)
        
        try:
            print("Step 1/7: Extracting features...")
            subprocess.run(["colmap", "feature_extractor", "--database_path", db_path, "--image_path", scans_dir], check=True)
            print("Step 2/7: Matching features...")
            subprocess.run(["colmap", "exhaustive_matcher", "--database_path", db_path], check=True)
            print("Step 3/7: Sparse reconstruction...")
            subprocess.run(["colmap", "mapper", "--database_path", db_path, "--image_path", scans_dir, "--output_path", sparse_dir], check=True)
            print("Step 4/7: Undistorting images...")
            subprocess.run(["colmap", "image_undistorter", "--image_path", scans_dir, "--input_path", os.path.join(sparse_dir, "0"), "--output_path", dense_dir], check=True)
            print("Step 5/7: Dense reconstruction...")
            subprocess.run(["colmap", "patch_match_stereo", "--workspace_path", dense_dir], check=True)
            print("Step 6/7: Stereo fusion...")
            subprocess.run(["colmap", "stereo_fusion", "--workspace_path", dense_dir, "--output_path", os.path.join(dense_dir, "fused.ply")], check=True)
            print("Step 7/7: Poisson meshing...")
            subprocess.run(["colmap", "poisson_mesher", "--input_path", os.path.join(dense_dir, "fused.ply"), "--output_path", output_file], check=True)
            print(f"Done! Created: {output_file}")
            return
        except subprocess.CalledProcessError as e:
            print(f"Error running COLMAP: {e}")
            sys.exit(1)
    elif engine == "local":
        print(f"Starting Apple Object Capture Engine (Local) on directory: {scans_dir}")
        output_file = os.path.join(scans_dir, f"reconstructed_model.{output_format}")
        
        # Check if mac_reconstruct binary exists
        script_dir = os.path.dirname(os.path.abspath(__file__))
        binary_path = os.path.join(script_dir, "mac_reconstruct")
        
        if not os.path.exists(binary_path):
            print("Error: mac_reconstruct binary not found. Please compile it first.")
            sys.exit(1)
            
        print("Running native macOS PhotogrammetrySession...")
        try:
            subprocess.run([binary_path, scans_dir, output_file], check=True)
            print(f"Done! Created: {output_file}")
            return
        except subprocess.CalledProcessError as e:
            print(f"Error running Apple Object Capture: {e}")
            sys.exit(1)
    
    # Create a mock file (empty file for testing UI integration)
    with open(output_file, "w") as f:
        if output_format == "stl":
            f.write(f"solid MOCK_{engine.upper()}_MESH\n")
            f.write("  facet normal 0 0 0\n    outer loop\n")
            f.write("      vertex 0 0 0\n      vertex 1 0 0\n      vertex 0 1 0\n")
            f.write("    endloop\n  endfacet\nendsolid MOCK_MESH\n")
        else:
            # Fake OBJ or 3MF string
            f.write(f"# MOCK {output_format.upper()} DATA FROM {engine.upper()} ENGINE\n")
            f.write("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
        
    print(f"Done! Created: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extension_3d_converter.py <scans_directory> [output_format] [engine]")
        sys.exit(1)
        
    target_dir = sys.argv[1]
    out_format = sys.argv[2] if len(sys.argv) > 2 else "3mf"
    engine_choice = sys.argv[3] if len(sys.argv) > 3 else "local"
    
    run_pipeline(target_dir, out_format, engine_choice)
