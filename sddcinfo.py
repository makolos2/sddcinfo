#  SDDCINFO - v2.5
#  By Michael Kolos
#  VMware Cloud on AWS Org / SDDC real-time reporting tool
#
# Change Log
#
# V 2.6 - April 1, 2024
#	- Change VPC & Public IP info to be reported only if the -n networking option is specified, as it requires NSX permissions.
#
# V 2.5 - March 31, 2023
#       - Changed to support Python v3
#       - Added detection + reporting status for VCDR recovery SDDC, NFS datastore attached, and NSX advanced add-on.
#       - Added reporting of Linked VPC, subnet & Managed Prefix-list status for the connected VPC.
#
# V 2.3 - June 1, 2022
#       - Added the vCenter URL to the output.
#
# V 2.2 - Aug. 18, 2020
#       - Added detection of multiple vR appliances for DRaaS at scale, and report the detected number along with the SRM status
#       - Added checks for the presence of networking information to avoid causing an error when no data was returned by the API.
#
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
parser.add_argument('-n','--networks', action="store_true", help="Include network segment and DX advertisement details in the console output only. Requires NSX access")
args = parser.parse_args()

### Access Token ###
authurl = 'https://console.cloud.vmware.com/csp/gateway/am/api/auth/api-tokens/authorize?refresh_token=%s' %(args.refreshtoken)
headers = {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
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
    org_type=orgjson["org_type"].encode()

# Iterate through each SDDC's JSON to pull relevent values
for sddc in sddcjson:
    if len(sddc)<1:
        continue
    #If SDDC is in FAILED status, let's print only that it's in a failed state and skip the rest
    if sddc["sddc_state"]=="FAILED":
        sddc_id = sddc["resource_config"]["sddc_id"].encode()
        print ("SDDC_ID %s is in a FAILED state") %(sddc_id)
        if args.writeslack:
            slackmsg += ", {\"type\": \"context\", \"elements\": [{ \"type\": \"mrkdwn\", \"text\": \"*FAILED SDDC :* %s\\nD\\n\"}]},{\"type\": \"divider\" }" %(sddc_id)
        continue
    # Get user Public IPs assigned
    publicipurl = sddc["resource_config"]["nsx_api_public_endpoint_url"].encode() + "/cloud-service/api/v1/public-ips/".encode()
    publicipresp = requests.get(publicipurl,headers=headers,data=payload)
    if publicipresp.status_code == 200:
        publicipjson = json.loads(publicipresp.text)
    if args.networks:
        # Get Connected VPC info (requires NSX access)
        vpcurl = sddc["resource_config"]["nsx_api_public_endpoint_url"].encode() + "/cloud-service/api/v1/linked-vpcs/".encode()
        vpcresp = requests.get(vpcurl,headers=headers,data=payload)
        if vpcresp.status_code == 200:
            vpcjson=json.loads(vpcresp.text)
            sddc_vpc = vpcjson["results"][0]["linked_vpc_addresses"][0].encode() + " Subnet: ".encode() + vpcjson["results"][0]["linked_vpc_subnets"][0]["cidr"].encode()
            if ("linked_vpc_managed_prefix_list_info" in vpcjson["results"][0]):
                if (vpcjson["results"][0]["linked_vpc_managed_prefix_list_info"]["managed_prefix_list_mode"]=="ENABLED"):
                    sddc_vpc += " MPL mode enabled".encode()
        # Get Network segments
        segmentsurl = sddc["resource_config"]["nsx_api_public_endpoint_url"].encode() + "/policy/api/v1/infra/tier-1s/cgw/segments".encode()
        segmentsresp = requests.get(segmentsurl,headers=headers,data=payload)
        if segmentsresp.status_code == 200:
            segmentsjson = json.loads(segmentsresp.text)
        # Get Learned routes
        learnedroutesurl = sddc["resource_config"]["nsx_api_public_endpoint_url"].encode() + "/cloud-service/api/v1/infra/external/routes/learned".encode()
        learnedroutesresp = requests.get(learnedroutesurl,headers=headers,data=payload)
        if learnedroutesresp.status_code == 200:
            learnedroutesjson = json.loads(learnedroutesresp.text)
        # Get advertised routes
        advroutesurl = sddc["resource_config"]["nsx_api_public_endpoint_url"].encode() + "/cloud-service/api/v1/infra/external/routes/advertised".encode()
        advroutesresp = requests.get(advroutesurl,headers=headers,data=payload)
        if advroutesresp.status_code == 200:
            advroutesjson = json.loads(advroutesresp.text)
    sddc_name = sddc["name"].encode()
    sddc_region = sddc["resource_config"]["region"].encode()
    sddc_id = sddc["resource_config"]["sddc_id"].encode()
    sddc_cidr = sddc["resource_config"]["agents"][0]["network_cidr"].encode()
    sddc_version = sddc["resource_config"]["sddc_manifest"]["vmc_internal_version"].encode()
    sddc_vcuuid = sddc["resource_config"]["vc_instance_id"].encode()
    sddc_vcurl = sddc["resource_config"]["vc_url"].encode()
    sddc_az1 = sddc["resource_config"]["availability_zones"][0].encode()
    if len(sddc["resource_config"]["availability_zones"])>1:
        sddc_az2 = sddc["resource_config"]["availability_zones"][1].encode()
        sddc_azs=sddc_az1.decode()+","+sddc_az2.decode()    
    else:
        sddc_azs=sddc_az1.decode()    
    if args.networks and (segmentsresp.status_code == 200):
        sddc_networks={}
        for segment in segmentsjson["results"]:
            if "subnets" in segment: 
                net=segment["subnets"][0]["network"].encode()
                type=segment["type"].encode()
                if not segment["id"] in ("sddc_vpc_reserved_segment_0", "cross_vpc_reserved_segment_0"):
                    sddc_networks[net]={}
                    sddc_networks[net]["type"]=type
            else:
                if "type" in segment:
                    if segment["type"].encode() == "EXTENDED":
                        name=segment["display_name"]
                        sddc_networks[name]={}
                        sddc_networks[name]["type"]="EXTENDED"
                    if segment["type"].encode() == "DISCONNECTED":
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
        cluster_name=cluster["cluster_name"].encode()
        sddc_clusters[cluster_name]={}
        sddc_clusters[cluster_name]["instance_type"] = cluster["esx_host_info"]["instance_type"].encode()
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
    print ("SDDC Name: {0}".format(sddc_name.decode()))
    print ("SDDC ID: {0}".format(sddc_id.decode()))
    print ("SDDC Region: {0}".format(sddc_region.decode()))
    print ("SDDC AZ: {0}".format(sddc_azs))
    print ("SDDC CIDR: {0}".format(sddc_cidr.decode()))
    print ("SDDC Version: {0}".format(sddc_version.decode()))
    print ("SDDC VC_UUID: {0}".format(sddc_vcuuid.decode()))
    print ("SDDC VC URL: {0}".format(sddc_vcurl.decode()))
    if vpcresp.status_code == 200:
        print ("Linked VPC: {0}".format(sddc_vpc.decode()))

    if args.writeslack:
        slackmsg += ", {\"type\": \"context\", \"elements\": [{ \"type\": \"mrkdwn\", \"text\": \"*SDDC Name:* %s\\n*SDDC ID:* %s\\n*SDDC Region:* %s *AZ:* %s\\n*SDDC CIDR:* %s\\n*SDDC Version:* %s\\n*SDDC VC_UUID:* %s\\n*SDDC VC URL:* %s\\n*Linked VPC:* %s\\n" %(sddc_name,sddc_id,sddc_region,sddc_azs,sddc_cidr,sddc_version,sddc_vcuuid,sddc_vcurl,sddc_vpc)

    # Check whether HCX manager entry exists
    if "HCX" in sddc["resource_config"]["management_vms"]: 
        print ("HCX is installed")
        if args.writeslack:
            slackmsg += "*HCX* is installed\\n"
    #Check state of NSX Advanced Add-on
    if (sddc["resource_config"]["nsxt_addons"] is not None):
        if (sddc["resource_config"]["nsxt_addons"]["enable_nsx_advanced_addon"] is True):
            print ("NSX Advanced Add-On is enabled")
            if args.writeslack:
                slackmsg += "*NSX Advanced Add-On* is *enabled*\\n"
    # Check whether any SRM instances exist
    if any(key.startswith("SRM-") for key in sddc["resource_config"]["management_vms"]):
        # Check whether multiple VR instances exist for scale
        if any(key.startswith("VRS-1") for key in sddc["resource_config"]["management_vms"]):
            print ("DRaaS is installed - 2 vR appliances")
            if args.writeslack:
                slackmsg += "*DRaaS* is installed - 2 vR appliances\\n"
        elif any(key.startswith("VRS-2") for key in sddc["resource_config"]["management_vms"]):
            print ("DRaaS is installed - 3 vR appliances")
            if args.writeslack:
                slackmsg += "*DRaaS* is installed - 3 vR appliances\\n"
        elif any(key.startswith("VRS-3") for key in sddc["resource_config"]["management_vms"]):
            print ("DRaaS is installed - 4 vR appliances")
            if args.writeslack:
                slackmsg += "*DRaaS* is installed - 4 vR appliances\\n"
        elif any(key.startswith("VRS-5") for key in sddc["resource_config"]["management_vms"]):
            print ("DRaaS is installed - 5 vR appliances")
            if args.writeslack:
                slackmsg += "*DRaaS* is installed - 5 vR appliances\\n"
        else:
            print ("DRaaS is installed - single vR appliances")
            if args.writeslack:
                slackmsg += "*DRaaS* is installed - single vR appliances\\n"
    # Check if SDDC is a VCDR recovery SDDC
    if (sddc["resource_config"]["vpc_info"]["vcdr_enis"] is not None):
        print ("Enabled as VCDR Recovery SDDC")
        if args.writeslack:
            slackmsg += "Enabled as VCDR Recovery SDDC\\n"
    # Check if NFS datastore attached (Only check if not a VCDR recovery SDDC, since that always has SCFS attached as NFS datastore)
    elif (sddc["resource_config"]["nfs_mode"] is True):
        print ("NFS Datastore attached")
        if args.writeslack:
            slackmsg += "NFS Datastore attached\\n"
    
    sddc_hosts=0
    for cluster in sddc_clusters:
        print ("Cluster Name: {0} - {1} {2} Hosts".format(cluster.decode(), sddc_clusters[cluster]["instance_type"].decode(), sddc_clusters[cluster]["count"]))
        sddc_hosts+=sddc_clusters[cluster]["count"]
        if args.writeslack:
            slackmsg += "*%s* - %s %s Hosts\\n" %(cluster, sddc_clusters[cluster]["instance_type"], sddc_clusters[cluster]["count"])
        org_hosts+=sddc_clusters[cluster]["count"]

    if publicipresp.status_code == 200:
        if "result_count" in publicipjson:
            print ("User Public IPs in SDDC: {0}\n".format(publicipjson["result_count"]))
            publiciptot+=publicipjson["result_count"]
            if args.writeslack:
                slackmsg += "*User Public IPs in SDDC:* %s\\n" %(publicipjson["result_count"])
    print ("Total Hosts in SDDC: {0}\n".format(sddc_hosts))
    if args.writeslack:
        slackmsg += "*Total Hosts in SDDC:* %s\\n\"}]}" %(sddc_hosts)
        slackmsg += ", {\"type\": \"divider\" }"

    if args.networks:
    # Print Network info for SDDC
        if segmentsresp.status_code == 200:
            print ("Compute Segments in SDDC: {0}".format(len(sddc_networks)))
        if advroutesresp.status_code == 200:
            if ("routes" in advroutesjson):
                for adv in advroutesjson["routes"]:
                    if (adv["connectivities"][0]["status"] == "SUCCEEDED"):
                        net=adv["destination"].encode()
                        path=adv["connectivities"][0]["connectivity_type"]
                        if net in sddc_networks:
                            sddc_networks[net]["advertised"]=path.encode()
                        else:
                            sddc_networks[net]={}
                            sddc_networks[net]["advertised"]=path.encode()
                            sddc_networks[net]["type"]=b"HCX/MGMT"
                for net in sorted(sddc_networks):
                    if ("advertised" in sddc_networks[net]):
                        print ("Network: {0:<18} Type: {1:<12} Advertised: {2}".format(net.decode(), sddc_networks[net]["type"].decode(), sddc_networks[net]["advertised"].decode()))
                    else:
                        print ("Network: {0:<18} Type: {1:<12} NOT Advertised".format(net.decode(), sddc_networks[net]["type"].decode()))
                for adv in learnedroutesjson["routes"]:
                    print ("DX Learned Route: {0:<18} Source: {1}".format(adv["destination"], adv["connectivities"][0]["connectivity_type"]))
            else:
                # If No DX, just list the compute segments
                for net in sorted(sddc_networks):
                    print ("Network: {0:<18} Type: {1:<12}".format(net, sddc_networks[net]["type"]))

    print ("\n")

# Don't print Org totals when a single SDDC was specified
if not args.sddcid:
    print ("Org Totals:\n ")
    if args.writeslack:
        slackmsg += ",{ \"type\": \"section\", \"text\": { \"type\": \"mrkdwn\", \"text\": \"*Org Totals:*\\n"

    # Instance type/count by region
    for region in instance_count:
        for instance in instance_count[region]:
            print ("{0} has {1} {2} instances\n".format(region.decode(), instance_count[region][instance], instance.decode()))
            if args.writeslack:
                slackmsg += "*%s* has *%s* *%s* instances\\n" %(region, instance_count[region][instance], instance)
    
    print ("Total Hosts per Region: ")
    for region in region_count:
       print ("{0} has {1} total hosts\n".format(region.decode(), region_count[region]))
       if args.writeslack:
           slackmsg += "*%s* has *%s* total hosts\\n" %(region, region_count[region])
    print ("Total User public IPs in Org: {0}".format(publiciptot))
    print ("Total Hosts in Org: {0}".format(org_hosts))
    print ("Total Clusters in Org: {0}".format(org_clusters))
    print ("Total SDDCs in Org: {0}\n\n".format(org_sddcs))
    print ("Org Type: {0}".format(org_type.decode()))

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

