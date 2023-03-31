# Sddcinfo
VMware Cloud on AWS SDDC/ORG reporting tool.


Outputs general SDDC state and configuration parameters for all SDDCs in an Org, as well as totals for host counts by instance type and region.
Can output report to console, or write to a slack webhook.
Optionally reports on networks and routing advertisement status.

# Installation
Requires python 3.x with modules:
- argparse (https://docs.python.org/3/library/argparse.html)
- operator (https://docs.python.org/3/library/operator.html)
- requests (https://pypi.org/project/requests/)

# Usage
```
usage: sddcinfo.py [-h] [-s SDDCID] [-W SLACKURL] [-n] orgid refreshtoken

Get the summary and consumption info for a VMC Org.

positional arguments:
  orgid                 the long ORG_ID to report on
  refreshtoken          a refresh token that has VMC administrator permissions
                        on the Org supplied

optional arguments:
  -h, --help            show this help message and exit
  -s SDDCID, --sddcid SDDCID
                        Optionally provide an SDDC ID. If omitted, all SDDCs
                        in the Org will be reported
  -W SLACKURL, --writeslack SLACKURL
                        Optionally provide a slack webhook URL and output a
                        slack-formatted message (using mrkdwn) to the webhook.
  -n, --networks        Include network segment and DX advertisement details
                        (displayed in the console output only).
```

# Known limitations
- Due to slack message limitations, the current slack format only supports < 33 SDDCs in the slack output. Console output doesn't have this limit. Need to support splitting slack output over multiple messages in this case. Currently slack just drops the message without posting it to the channel.
- Due to a VMC issue, with 1.8 version SDDCs, the networking advertisement information doesn't work in most cases.
- Cannot disable console output
- Networking details are not included in the slack webhook output (due to length of content and above noted slack message limitations)



