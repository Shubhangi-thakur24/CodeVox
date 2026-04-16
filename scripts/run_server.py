# scripts/run_server.py
import uvicorn
import os
import ssl
import urllib3
import shutil
from pyngrok import ngrok, conf
from dotenv import load_dotenv

def main() -> None:
    # Load environment variables
    load_dotenv()
    
    # Change to the project root directory (CodeVox)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)
    
    print("Starting CodeVox Webhook Server...")
    print("Using app: src.webhook_server:app")
    print("Local endpoint: http://localhost:8000/vapi/webhook")
    print("Health: http://localhost:8000/health")
    
    # Fix SSL certificate verification issues
    # Disable urllib3 SSL warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Configure ngrok with updated certificates
    try:
        import certifi
        ngrok_config = conf.get_default()
        ngrok_config.ca_certs = certifi.where()
    except ImportError:
        print("Note: certifi not found, using system certificates")
    
    # Clean up old ngrok processes
    print("Checking ngrok binary version...")
    try:
        from pyngrok import process
        # Kill existing processes
        process.kill_all()
        print("Killed existing ngrok processes")
    except:
        pass
    
    # Set ngrok auth token if provided
    auth_token = os.getenv("NGROK_AUTH_TOKEN")
    if auth_token:
        ngrok.set_auth_token(auth_token)
        print("Ngrok auth token set.")
    else:
        print("Warning: No NGROK_AUTH_TOKEN found. Ngrok may require authentication.")
    
    # Kill any existing tunnels
    print("Stopping any existing ngrok tunnels...")
    try:
        ngrok.kill()
    except:
        pass
    
    # Start ngrok tunnel
    print("Starting ngrok tunnel...")
    try:
        public_url = ngrok.connect(8000)
        print(f"Public URL: {public_url}")
        print("Press Ctrl+C to stop")
    except Exception as e:
        error_msg = str(e)
        if "already online" in error_msg or "ERR_NGROK_334" in error_msg:
            print("⚠️ Ngrok tunnel conflict detected.")
            print("💡 Skipping ngrok tunnel for now - server will run locally only.")
            print("💡 Local endpoint: http://localhost:8000/vapi/webhook")
            print("💡 To fix ngrok: run 'ngrok kill' in terminal, then restart server.")
            public_url = "http://localhost:8000"
            print("Press Ctrl+C to stop")
        else:
            print(f"❌ Ngrok error: {error_msg}")
            print("💡 Running server locally without ngrok tunnel.")
            public_url = "http://localhost:8000"
            print("Press Ctrl+C to stop")
    
    uvicorn.run("src.webhook_server:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()