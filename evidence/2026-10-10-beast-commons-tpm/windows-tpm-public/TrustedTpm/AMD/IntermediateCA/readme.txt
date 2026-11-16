For HSP TPMs, AMD uses  intermediate CA cert(Microsoft Pluton Policy CA A.cer) that is signed by a MSFT root CA(Microsoft Pluton Root CA 2021.cer) to sign
per device intermediate certs(Pluton-Factory-DEVICE-EK-ICA-DFID0001.cer and Pluton-Factory-FIPS-EK-ICA-DFID0001.cer) which are used to sign the EK certificates.

EkChains: ..\cab\AMD\RootCA\Microsoft Pluton Root CA 2021.cer,..\cab\AMD\IntermediateCA\Microsoft Pluton Policy CA A.cer,..\cab\AMD\IntermediateCA\Pluton-Factory-FIPS-EK-ICA-DFID0001.cer
          ..\cab\AMD\RootCA\Microsoft Pluton Root CA 2021.cer,..\cab\AMD\IntermediateCA\Microsoft Pluton Policy CA A.cer,..\cab\AMD\IntermediateCA\Pluton-Factory-DEVICE-EK-ICA-DFID0001.cer

Since these HSP devices calculate the AIK Alias using MSFT as the manufacturer, the AIK certificates also use the MSFT and NOT AMD in the calculated guid for the AIK alias.
