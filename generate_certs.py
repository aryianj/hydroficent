import ipaddress
from datetime import datetime, timedelta, timezone # for setting valid from and valid until
from pathlib import Path # file path handling

from cryptography import x509 # certificate building library
from cryptography.x509.oid import NameOID # standard identifiers for certificate fields
from cryptography.hazmat.primitives import hashes, serialization # SHA256 & saving certificates to files
from cryptography.hazmat.primitives.asymmetric import rsa # RSA key generation

def generate_ca_certificate():
    print('\n[1 / 3] Generating Authority (CA)...')

    # Generate private key for CA
    print('        Generating CA private key (2048 bits)...')
    ca_key = rsa.generate_private_key(
        public_exponent=65537, # standard, secure value
        key_size=2048, # 2048-bit encryption for learning (production might use 4096)
    )

    # Define the CA's identity
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Grand Marina Hotel'),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Water Systems Security"),
        x509.NameAttribute(NameOID.COMMON_NAME, 'Grand Marina Root CA'),
    ])

    # Build and sign the CA certificate
    print('        Creating CA certificate (valid for 10 years)...')
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name) # self-signed: issuer = subject
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650)) # 3650 = 10 years
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    print('        CA certificate created successfully!')
    return ca_key, ca_cert


def generate_server_certificate(ca_key, ca_cert):
    print('[2 / 3] Generating Sever Certificate...')

    print('        Generating server private key (2048 bits)...')
    server_key = rsa.generate_private_key(
        public_exponent=65537, 
        key_size=2048, 
    )
    
    server_name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Grand Marina Hotel'),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "MQTT Broker"),
        x509.NameAttribute(NameOID.COMMON_NAME, 'localhost'),
    ])

    print('        Creating server certificate (valid for 1 year)...')
    print('        Common Name: localhost')
    print('        Subject Alternative Names: localhost, 127.0.0.1')
    server_cert = (
            x509.CertificateBuilder()
            .subject_name(server_name)
            .issuer_name(ca_cert.subject)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365)) 
            .add_extension(
                x509.SubjectAlternativeName([ # certificate works for all listed names
                    x509.DNSName('localhost'),
                    x509.IPAddress(ipaddress.IPv4Address('127.0.0.1'))
                ]),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )

    print('        Server certificate created successfully!')
    return server_cert, server_key

def save_certificates(ca_cert, server_cert, server_key, output_dir='certs'):
    print('[3 / 3] Saving certificates to certs/ folder...')

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # Save CA certificate (public)
    with open(output_path / 'ca.pem', 'wb') as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    print('        Saved: certs\ca.pem...')


    # Save server certificate (public)
    with open(output_path / 'server.pem', 'wb') as f:
        f.write(server_cert.public_bytes(serialization.Encoding.PEM))
    print('        Saved: certs\server.pem...')

    # Save server private key 
    with open(output_path / 'server-key.pem', 'wb') as f:
        f.write(server_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    print('        Saved: certs\server-key.pem...')

    print('        Verifying certificates...')
    print(f'        CA Subject: {ca_cert.subject}')
    print(f'        CA Valid Until: {ca_cert.not_valid_after_utc}')
    print(f'        Server Subject: {server_cert.subject}')
    print(f'        Server Issuer: {server_cert.issuer}')
    print(f'        Server Valid Until: {server_cert.not_valid_after_utc}')
    print(f'        Chain verified: Server cert is signed by CA')

print('=' * 50)
print('    Certificate Generation for Grand Marina Hotel')
print('=' * 50)

ca_key, ca_cert = generate_ca_certificate()
server_cert, server_key = generate_server_certificate(ca_key, ca_cert)
save_certificates(ca_cert, server_cert, server_key)

print('=' * 50)
print('    Certificate generated successfully')
print('=' * 50)
print('\n Files created:')
print('  certs\ca.pem')
print('  certs\server.pem')
print('  certs\server-key.pem')
