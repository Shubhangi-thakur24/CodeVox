# src/cli.py
import click
import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

# Use ngrok URL in dev, or production URL later
API_BASE = os.getenv("CODEVOX_API_URL", "http://localhost:8000")

@click.group()
def cli():
    """CodeVox: Voice-First Developer Assistant"""
    pass

@cli.command()
@click.argument('query')
def ask(query):
    """Ask a question about your codebase (Text-to-Text mode)."""
    click.echo(f" Asking CodeVox: '{query}'...")
    
    payload = {
        "type": "message",
        "message": {
            "role": "user",
            "content": query
        }
    }
    
    try:
        resp = requests.post(f"{API_BASE}/vapi/webhook", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if "messages" in data and len(data["messages"]) > 0:
            answer = data["messages"][0]["content"]
            click.echo(f"\nCodeVox: {answer}\n")
        else:
            click.echo("No response received.")
            
    except requests.exceptions.ConnectionError:
        click.echo("Error: Cannot connect to server. Is 'run_server.py' running?")
    except Exception as e:
        click.echo(f"Error: {str(e)}")

@cli.command()
@click.argument('error_log', type=click.File('r'))
def debug(error_log):
    """Analyze a specific error log file."""
    content = error_log.read()
    query = f"I have this error:\n{content}\nWhat is causing it and how do I fix it?"
    
    click.echo("Analyzing error log...")
    # Reuse the ask logic
    ctx = ask.make_context('ask', [query])
    with ctx:
        return ctx.invoke(ask.callback, query=query)

if __name__ == '__main__':
    cli()