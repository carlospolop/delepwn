import sys
import yaml
import argparse
from google.auth.credentials import Credentials
from delepwn.core.enumerator import ServiceAccountEnumerator
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from delepwn.core.oauth_enumerator import OAuthEnumerator
from delepwn.core.domain_users import DomainUserEnumerator
import os
import traceback
from datetime import datetime
from delepwn.utils.output import print_color
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from delepwn.config.settings import SERVICE_ACCOUNT_KEY_FOLDER


SCOPES_FILE = 'delepwn/config/oauth_scopes.txt'  # Updated path


def results(oauth_enumerator):
    """
    Write enumeration results to a file in the results directory
    Args:
        oauth_enumerator: The OAuthEnumerator instance containing results
    """
    # Create results directory if it doesn't exist
    result_folder = 'results'
    os.makedirs(result_folder, exist_ok=True)

    # Generate filename with datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"delepwn_enum_{timestamp}.txt"
    filepath = os.path.join(result_folder, filename)

    valid_results = oauth_enumerator.get_valid_results()
    
    if not valid_results:
        print("\n[!] No valid results found to save.")

    with open(filepath, 'w') as f:
        # Write header
        f.write("=" * 50 + "\n")
        f.write("DelePwn Enum Scan Results\n")
        f.write(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 50 + "\n\n")

        # Write results for each service account
        for json_path, valid_scopes in valid_results.items():
            if valid_scopes:
                # Service Account section
                f.write("-" * 40 + "\n")
                f.write(f"Service Account enabled for DWD: {os.path.basename(json_path)}\n")
                f.write("-" * 40 + "\n")
                
                # OAuth Scopes section
                f.write("\nValid OAuth Scopes:\n")
                for scope in valid_scopes:
                    f.write(f"  • {scope}\n")
                f.write("\n")
    print_color(f"\n[+] Results saved to {filepath}", color="blue")

    return filepath



def check(enumerator, testEmail, verbose, enum_output):
    try:
        enumerator.enumerate_service_accounts()

        if testEmail:
            print_color(f"\n[*] Using provided test email: {testEmail}", color="white")
            # Create a dictionary with the test email in the same format as single_test_email
            domain = testEmail.split('@')[1]
            test_email_dict = {domain: testEmail}
            oauth_enumerator = OAuthEnumerator(enumerator, SCOPES_FILE, SERVICE_ACCOUNT_KEY_FOLDER, test_email_dict, verbose=verbose)
        else:
            # If no test email provided, enumerate users to find one
            domain_user_enumerator = DomainUserEnumerator(enumerator)
            domain_user_enumerator.print_unique_domain_users()
            oauth_enumerator = OAuthEnumerator(enumerator, SCOPES_FILE, SERVICE_ACCOUNT_KEY_FOLDER, domain_user_enumerator.single_test_email, verbose=verbose)

        print_color("\n[*] Enumerating OAuth scopes and private key access tokens... (it might take a while based on the number of the JWT combinations)\n", color="yellow")
        oauth_enumerator.run()
        confirmed_dwd_keys = oauth_enumerator.confirmed_dwd_keys
        enumerator.key_creator.delete_keys_without_dwd(confirmed_dwd_keys)

        if enum_output:
            results(oauth_enumerator)
    except Exception as e:
        print_color(f"An error occurred: {e}", color="red")
        traceback.print_exc()

def test_service_account_key(credentials, args, verbose=False):
    """Test a service account key file for Domain-Wide Delegation privileges"""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import google.auth.transport.requests
    
    # Create custom credentials and enumerator
    try:
        enumerator = ServiceAccountEnumerator(credentials, verbose=verbose)
        domain_user_enumerator = DomainUserEnumerator(enumerator)
        
        # Try to get a valid domain user
        test_user = args.email
        if not test_user:
            test_user = domain_user_enumerator.get_first_valid_domain_user()
            if test_user:
                print_color(f"\n✓ Found valid domain user to test: {test_user}", color="green")
            else:
                print_color("\n[-] Could not find valid domain user to test", color="red")
                sys.exit(1)
    except Exception as e:
        print_color(f"\n[-] Error during enumeration: {str(e)}", color="red")
        if verbose:
            traceback.print_exc()
        sys.exit(1)

    # Read all OAuth scopes from the file
    with open(SCOPES_FILE, 'r') as file:
        test_scopes = [line.strip() for line in file.readlines()]
    
    print_color("\nTesting for Domain-Wide Delegation privileges...", color="cyan")
    
    
    authorized_scopes = []
    
    for scope in test_scopes:
        try:
            # Try to create delegated credentials
            delegated_credentials = credentials.with_subject(test_user)
            delegated_credentials = delegated_credentials.with_scopes([scope])
            
            # Try to refresh the token
            request = google.auth.transport.requests.Request()
            delegated_credentials.refresh(request)
            
            authorized_scopes.append(scope)
            if verbose:
                print_color(f"✓ Successfully authorized scope: {scope}", color="green")
                
        except Exception as e:
            if verbose:
                print_color(f"× Failed to authorize scope: {scope}", color="red")
                print_color(f"  Error: {str(e)}", color="red")
    
    # Print results
    if authorized_scopes:
        print_color("\n[!] Service account has Domain-Wide Delegation enabled!", color="yellow")
        print_color("\nAuthorized scopes:", color="green")
        for scope in authorized_scopes:
            print_color(f"  ✔ {scope}", color="green")
    else:
        print_color("\n[-] Service account does not have Domain-Wide Delegation privileges", color="red")