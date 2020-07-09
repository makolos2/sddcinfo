#  SDDCINFO - v2.1
#  By Michael Kolos
#  VMware Cloud on AWS Org / SDDC real-time reporting tool
#
# Change Log
# V 2.1 - May 4, 2020
# Added support for printing network info for SDDCs by adding the -n flag.
#       - Prints list of compute segments and their type
#       - If a DX is connected, also indicates whether the networks advertised and learned over the DX
#       - Network info is NOT included in the slack output, if slack webhook is specified.


# V 1.0 
# Initial version
#   - Supports printing out SDDC identification and consumption details, including IDs, location, and add-on status
#   - Prints Clusters by size and type for each SDDC
#   - Prints ORG level summary with breakdown by host type by region
#   - If a single SDDC is specified using the -s option, ORG totals are not printer
#   - Provides the option to print the output to a Slack Webhook, using mrkdwn formatting, as a single message for all output. This has a limit of about 40 SDDCs, as slack messages are limited to 50 sections.





### Package Imports ####
import requests
import json
import argparse
from operator import itemgetter

### Ready arguments from command line ###
parser = argparse.ArgumentParser(description='Get the summary and consumption info for a VMC Org.')
parser.add_argument('orgid', help="the long ORG_ID to report on")
parser.add_argument('refreshtoken', help="a refresh token that has VMC administrator permissions on the Org supplied")
parser.add_argument('-s','--sddcid', help="Optionally provide an SDDC ID.  If omitted, all SDDCs in the Org will be reported")
parser.add_argument('-W','--writeslack', help="Optionally provide a slack webhook URL and output a slack-formatted message to the webhook.")
parser.add_argument('-n','--networks', action="store_true", help="Include network segment and DX advertisement details in the console output only.")
args = parser.parse_args()

### Access Token ###
authurl = 'https://console.cloud.vmware.com/csp/gateway/am/api/auth/api-tokens/authorize?refresh_token=%s' %(args.refreshtoken)
headers = {'Accept': 'application/json'}
payload = {}
authresp = requests.post(authurl,headers=headers,data=payload)
authjson = json.loads(authresp.text)
token = authjson["access_token"]

if args.sddcid:
    infourl = "https://vmc.vmware.com/vmc/api/orgs/%s/sddcs/%s" %(args.orgid,args.sddcid)
else:
    infourl = "https://vmc.vmware.com/vmc/api/orgs/%s/sddcs" %(args.orgid)
orgurl = "https://vmc.vmware.com/vmc/api/orgs/%s" %(args.orgid)
headers = {'csp-auth-token': token, 'content-type': 'application/json'}
payload = {}
sddcresp = requests.get(infourl,headers=headers,data=payload)
sddcjson = json.loads(sddcresp.text)
orgresp = requests.get(orgurl,headers=headers,data=payload)
orgjson = json.loads(orgresp.text)
org_hosts=0
org_sddcs=0
org_clusters=0
region_count={}
instance_count={}
publiciptot=0
sddc_az2=""
slackmsg="{ \"blocks\": [ {\"type\": \"divider\" }"

# Check if only a single SDDC is returned. If so, add a blank entry to put it into list format
if "resource_config" in sddcjson:
    sddcjson=['',sddcjson]
else:
    # Since we're returning an org here, get the org_type value too
    org_type=orgjson["org_type"].encode("ascii")

# Iterate through each SDDC's JSON to pull relevent values
for sddc in sddcjson:
    if len(sddc)<1:
        continue
    # Get user Public IPs assigned
    publicipurl = sddc["resource_config"]["nsx_api_public_endpoint_url"].encode("ascii") + "/cloud-service/api/v1/public-ips/".encode("ascii")
    publicipresp = requests.get(publicipurl,headers=headers,data=payload)
    publicipjson = json.loads(publicipresp.text)
    if args.networks:
        # Get Network segments
        segmentsurl = sddc["resource_config"]["nsx_api_public_endpoint_url"].encode("ascii") + "/policy/api/v1/infra/tier-1s/cgw/segments".encode("ascii")
        segmentsresp = requests.get(segmentsurl,headers=headers,data=payload)
        segmentsjson = json.loads(segmentsresp.text)
        # Get Learned routes
        learnedroutesurl = sddc["resource_config"]["nsx_api_public_endpoint_url"].encode("ascii") + "/cloud-service/api/v1/infra/external/routes/learned".encode("ascii")
        learnedroutesresp = requests.get(learnedroutesurl,headers=headers,data=payload)
        learnedroutesjson = json.loads(learnedroutesresp.text)
        # Get advertised routes
        advroutesurl = sddc["resource_config"]["nsx_api_public_endpoint_url"].encode("ascii") + "/cloud-service/api/v1/infra/external/routes/advertised".encode("ascii")
        print advroutesurl
        advroutesresp = requests.get(advroutesurl,headers=headers,data=payload)
        advroutesjson = json.loads(advroutesresp.text)
    sddc_name = sddc["name"].encode("utf-8")
    sddc_region = sddc["resource_config"]["region"].encode("ascii")
    sddc_id = sddc["resource_config"]["sddc_id"].encode("ascii")
    sddc_cidr = sddc["resource_config"]["agents"][0]["network_cidr"].encode("ascii")
    sddc_version = sddc["resource_config"]["sddc_manifest"]["vmc_internal_version"].encode("ascii")
    sddc_vcuuid = sddc["resource_config"]["vc_instance_id"].encode("ascii")
    sddc_az1 = sddc["resource_config"]["availability_zones"][0].encode("ascii")
    if len(sddc["resource_config"]["availability_zones"])>1:
        sddc_az2 = sddc["resource_config"]["availability_zones"][1].encode("ascii")
        sddc_azs=sddc_az1+","+sddc_az2    
    else:
        sddc_azs=sddc_az1    
    if args.networks:
        sddc_networks={}
        for segment in segmentsjson["results"]:
            if "subnets" in segment: 
                net=segment["subnets"][0]["network"].encode("ascii")
                type=segment["type"].encode("ascii")
                if not segment["id"] in ("sddc_vpc_reserved_segment_0", "cross_vpc_reserved_segment_0"):
                    sddc_networks[net]={}
                    sddc_networks[net]["type"]=type
            else:
                if "type" in segment:
                    if segment["type"].encode("ascii") == "EXTENDED":
                        name=segment["display_name"]
                        sddc_networks[name]={}
                        sddc_networks[name]["type"]="EXTENDED"
                    if segment["type"].encode("ascii") == "DISCONNECTED":
                        name=segment["display_name"]
                        sddc_networks[name]={}
                        sddc_networks[name]["type"]="DISCONNECTED"
    sddc_clusters={}
    org_sddcs+=1
    # Create a counter for the region
    if not sddc_region in region_count:
        region_count[sddc_region] = 0 
        instance_count[sddc_region] = {}
    # Count the number of clusters
    for cluster in sddc["resource_config"]["clusters"]:
        cluster_name=cluster["cluster_name"].encode("ascii")
        sddc_clusters[cluster_name]={}
        sddc_clusters[cluster_name]["instance_type"] = cluster["esx_host_info"]["instance_type"].encode("ascii")
        sddc_clusters[cluster_name]["count"] = 0
        org_clusters+=1
        instance_type=sddc_clusters[cluster_name]["instance_type"]
        # Count the number of ESXi hosts in each cluster, sddc, region and instance type
        for esx in cluster["esx_host_list"]:
            sddc_clusters[cluster_name]["count"] += 1
            region_count[sddc_region] += 1
            if instance_type in instance_count[sddc_region]:
                instance_count[sddc_region][instance_type] += 1
            else:
                 instance_count[sddc_region][instance_type] = 1

    # Print out SDDC Identity Infos
    print ("SDDC Name: %s" %(sddc_name))
    print ("SDDC ID: %s") %(sddc_id)
    print ("SDDC Region: %s") %(sddc_region)
    print ("SDDC AZ: %s") %(sddc_azs)
    print ("SDDC CIDR: %s") %(sddc_cidr)
    print ("SDDC Version: %s") %(sddc_version)
    print ("SDDC VC_UUID: %s") %(sddc_vcuuid)
    
    if args.writeslack:
        slackmsg += ", {\"type\": \"context\", \"elements\": [{ \"type\": \"mrkdwn\", \"text\": \"*SDDC Name:* %s\\n*SDDC ID:* %s\\n*SDDC Region:* %s *AZ:* %s\\n*SDDC CIDR:* %s\\n*SDDC Version:* %s\\n*SDDC VC_UUID:* %s\\n" %(sddc_name,sddc_id,sddc_region,sddc_azs,sddc_cidr,sddc_version,sddc_vcuuid)

    # Check whether HCX manager entry exists
    if "HCX" in sddc["resource_config"]["management_vms"]: 
        print ("HCX is installed")
        if args.writeslack:
            slackmsg += "*HCX* is installed\\n"
    # Check whether any SRM instances exist
    if any(key.startswith("SRM-") for key in sddc["resource_config"]["management_vms"]):
        print ("DRaaS is installed")
        if args.writeslack:
            slackmsg += "*DRaaS* is installed\\n"
    sddc_hosts=0
    for cluster in sddc_clusters:
        print ("Cluster Name: %s - %s %s Hosts") %(cluster, sddc_clusters[cluster]["instance_type"], sddc_clusters[cluster]["count"])
        sddc_hosts+=sddc_clusters[cluster]["count"]
        if args.writeslack:
            slackmsg += "*%s* - %s %s Hosts\\n" %(cluster, sddc_clusters[cluster]["instance_type"], sddc_clusters[cluster]["count"])
        org_hosts+=sddc_clusters[cluster]["count"]
    
    if "result_count" in publicipjson:
        print ("User Public IPs in SDDC: %s\n") %(publicipjson["result_count"])
        publiciptot+=publicipjson["result_count"]
        if args.writeslack:
            slackmsg += "*User Public IPs in SDDC:* %s\\n" %(publicipjson["result_count"])
    print ("Total Hosts in SDDC: %s\n") %(sddc_hosts)
    if args.writeslack:
        slackmsg += "*Total Hosts in SDDC:* %s\\n\"}]}" %(sddc_hosts)
        slackmsg += ", {\"type\": \"divider\" }"

    if args.networks:
    # Print Network info for SDDC
        if sddc_networks: 
            print ("Compute Segments in SDDC: %s") %(len(sddc_networks))
            if ("routes" in advroutesjson):
                for adv in advroutesjson["routes"]:
                    if (adv["connectivities"][0]["status"].encode("ascii") == "SUCCEEDED"):
                        net=adv["destination"].encode("ascii")
                        path=adv["connectivities"][0]["connectivity_type"].encode("ascii")
                        if net in sddc_networks:
                            sddc_networks[net]["advertised"]=path
                        else:
                            sddc_networks[net]={}
                            sddc_networks[net]["advertised"]=path
                            sddc_networks[net]["type"]="HCX/MGMT"
                for net in sorted(sddc_networks):
                    if ("advertised" in sddc_networks[net]):
                        print ("Network: %-18s Type: %-12s Advertised: %s") %(net, sddc_networks[net]["type"], sddc_networks[net]["advertised"])
                    else:
                        print ("Network: %-18s Type: %-12s NOT Advertised") %(net, sddc_networks[net]["type"])
                for adv in learnedroutesjson["routes"]:
                    print ("DX Learned Route: %18s Source: %s") %(adv["destination"].encode("ascii"), adv["connectivities"][0]["connectivity_type"].encode("ascii"))
            else:
                # If No DX, just lst the compute segments
                for net in sorted(sddc_networks):
                    print ("Network: %-18s Type: %-12s") %(net, sddc_networks[net]["type"])
    print ("\n")

# Don't print Org totals when a single SDDC was specified
if not args.sddcid:
    print ("Org Totals:\n ")
    if args.writeslack:
        slackmsg += ",{ \"type\": \"section\", \"text\": { \"type\": \"mrkdwn\", \"text\": \"*Org Totals:*\\n"

    # Instance type/count by region
    for region in instance_count:
        for instance in instance_count[region]:
            print ("%s has %s %s instances\n") %(region, instance_count[region][instance], instance)
            if args.writeslack:
                slackmsg += "*%s* has *%s* *%s* instances\\n" %(region, instance_count[region][instance], instance)
    
    print ("Total Hosts per Region: ")
    for region in region_count:
       print ("%s has %s total hosts\n") %(region, region_count[region])
       if args.writeslack:
           slackmsg += "*%s* has *%s* total hosts\\n" %(region, region_count[region])
    print ("Total User public IPs in Org: %s") %(publiciptot)
    print ("Total Hosts in Org: %s") %(org_hosts)
    print ("Total Clusters in Org: %s") %(org_clusters)
    print ("Total SDDCs in Org: %s\n\n") %(org_sddcs)
    print ("Org Type: %s") %(org_type)

    if args.writeslack:
        slackmsg += "*Total User public IPs in Org:* %s\\n" %(publiciptot)
        slackmsg += "*Total Hosts in Org:* %s\\n" %(org_hosts)
        slackmsg += "*Total Clusters in Org:* %s\\n" %(org_clusters)
        slackmsg += "*Total SDDCs in Org:* %s\"}}]}" %(org_sddcs)
else:
    slackmsg += "] }"

if args.writeslack:
    headers = {'Accept': 'application/json'}
    authresp = requests.post(args.writeslack,headers=headers,data=slackmsg)
    print (authresp)

