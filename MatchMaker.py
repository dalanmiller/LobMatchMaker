#!/usr/bin/env python
# -*- coding: utf-8 -*-

from argparse import ArgumentParser
from clint.eng import join
from clint.textui import puts, colored, indent, columns
from requests_futures.sessions import FuturesSession
import json
import os
import requests
import sys
import time

access_token = "GET YOUR OWN TOKEN"


def query_jobs(skill_ids, matches=1, limit=10, city=False):
    """
    Method which makes the http requests to the AngelList API to retrieve
    jobs given the skill_ids provided. Returns a list the length of the
    provided limit parameter and jobs which contain at least the amount
    of provided matches via the matches paramter
    """

    url = "https://api.angel.co/1/tags/{}/jobs"

    #Create a list of urls for each skill id to retrieve jobs which have that id
    urls = [url.format(s) for s in skill_ids]

    sessions = []

    #Setup the params and future session object
    params = dict(access_token=access_token)
    session = FuturesSession(max_workers=10)

    #For each constructed url append the HTTP session to the list of sessions
    for u in urls:
        sessions.append(session.get(u, params=params))

    #While not all the sessions are complete, wait for them to complete
    while(not all([x.done() for x in sessions])):
        time.sleep(0.20)

    #Want to ensure that I don't have a list with duplicates
    jobs = {}

    #Iterate through each session and load the JSON
    for s in sessions:
        jobs_list = s.result().json()['jobs']

        #For each job in the returned JSON ensure that it isn't already in the list
        # and add if not, also add the skill_tags key for later easy processing
        for j in jobs_list:
            if j['id'] not in jobs:

                j["skill_tags"] = \
                    [x['id'] for x in j['tags'] if x['tag_type'] == "SkillTag"]

                jobs[j['id']] = j

    jobs = jobs.values()

    #If the city filter is provided
    new_jobs = []
    if city and type(city) == int:
        for j in jobs:
            for t in j["tags"]:
                if t["tag_type"] == "LocationTag" and t["id"] == city:
                    new_jobs.append(j)
                    break

        jobs = new_jobs

    elif type(city) == str:
        url = "https://api.angel.co/1/search?query={}&type=LocationTag"
        url = url.format(city)
        response = requests.get(url)
        response_json = response.json()

        if len(response_json) > 0:
            city = response_json[0]['id']

            for j in jobs:
                for t in j["tags"]:
                    if t["tag_type"] == "LocationTag" and t["id"] == city:
                        new_jobs.append(j)
                        break

            jobs = new_jobs

    #If we want to show only matches greater than a certain threshold
    if matches > 1:
        skill_ids_set = set(skill_ids)
        jobs = filter(lambda j: len(skill_ids_set & set(j['skill_tags'])) >= matches, jobs)

    #Sort jobs descending based on number of skills in common with user
    s_jobs = sorted(jobs,
                    key=lambda j: len(set(skill_ids) & set(j['skill_tags'])),
                    reverse=True)

    return s_jobs[:limit]



def print_job(i, job, user_skill_ids):
    """
    Print job function which takes a job JSON representation and a set of
    user skill ids and formats the output
    """

    with indent(2, quote=colored.blue('.')):

        #Output Title | Company | Salary
        title_text = \
            colored.magenta(str(i) + ") ") + \
            job["title"] + \
            " | " + \
            colored.blue(job["startup"]["name"])

        #Find the location tag if it exists and add it to the title string
        for x in job["tags"]:
            if x["tag_type"] == "LocationTag":
                title_text += " | " + colored.red(x["name"].title())
                break

        #Ensure salary exists and add it to title output string
        if "salary_max" in job and "salary_min" in job and "salary_max" != 0:
            title_text += \
                " | " + \
                colored.green("$" + str(job["salary_min"])) + \
                " ~ " + \
                colored.green("$" + str(job["salary_max"]))

        puts(title_text)

        #Output each skill and change color depending if the user has the skill
        matched_skills = []
        non_matched_skills = []
        for skill in (x for x in job['tags'] if x['tag_type'] == "SkillTag"):
            if skill['id'] in user_skill_ids:
                matched_skills.append(colored.yellow(skill['name']))
            else:
                non_matched_skills.append(colored.cyan(skill['name']))

        matched_skills = map(str, matched_skills)
        non_matched_skills = map(str, non_matched_skills)
        puts()
        puts(
             colored.yellow(
                    "MATCHED SKILLS | " +
                    join(matched_skills, conj="", separator="")))

        puts(
             colored.cyan(
                    "OTHER SKILLS   | " +
                    join(non_matched_skills, conj="", separator="")))
        puts()

        if 'description' in job and job['description']:

            #Construct the description column
            desc_text = (job['description'][:250] + '..') \
                if len(job['description']) > 250 \
                else job['description']

            desc_text = desc_text.encode("utf8")
        else:
            desc_text = "No description provided"

        #Column char width

        desc_col = 80

        puts(columns([(colored.red("DESCRIPTION")), desc_col]))
        with indent(2):
            puts(columns([desc_text, desc_col]))

        puts("\n")

if __name__ == "__main__":

    parser = ArgumentParser(usage="AngelList API Job Searcher")
    parser.add_argument("-m", action="store", dest="matches", default=1,
                        help="Number of matches required", type=int)
    parser.add_argument("-l", action="store", dest="limit", default=10,
                        help="Maximum number of results", type=int)
    parser.add_argument("-c", action="store_true", dest="city",
                        help="City flag which specifies that the city must \
                        match the provider user's city")
    parser.add_argument("-cc", action="store", dest="ccity",
                        help="Custom city flag which specifies that the city must \
                        match the provider city")
    parser.add_argument('path', action="store")

    results = parser.parse_args()

    sys.path.insert(0, os.path.abspath('..'))

    #Determine if the passed argument is a path to a file or not
    if "http" in results.path:

        #Assume only one argument is passed that is not a flag
        url = results.path

        #Response from the HTTP request
        response = requests.get(url)

        #User dictionary created from response json -> dict method
        user = response.json()

    else:

        #Open up file and read it
        with open(os.path.abspath(results.path), "r") as f:
            user = json.loads(f.read(), encoding="utf-8")

    #If matches flag supplied use provided value otherwise 1 match required
    matches = results.matches

    #If limit flag supplied use provided value otherwise 10 results
    limit = results.limit

    #Set city parameter which is default False
    if results.city and "locations" in user and len(user["locations"]) > 0:
        city = user["locations"][0]["id"]
    elif results.ccity:
        city = results.ccity
    else:
        city = False

    #Get raw list of skill ids from user
    skill_ids = [x['id'] for x in user['skills']]

    jobs = query_jobs(skill_ids, matches=matches, limit=limit, city=city)

    if jobs > 0:
        puts(colored.green("===================================="))
        puts(colored.green('========== Jobs Found - {:2d} =========\n'.format(len(jobs))))

        for i, j in enumerate(jobs, 1):
            print_job(i, j, skill_ids)

    else:
        puts(colored.red("===================================="))
        puts(colored.red("========= No Jobs Found :( =========\n"))

