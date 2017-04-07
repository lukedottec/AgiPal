# extract.py

import re
import os
import time
import queue
import pickle
import subprocess
from datetime import datetime

# Personal classes
from util import *
from entity import *
from experience import *

# Directories of interest
base_repo_dir = "../../../Repos/"
repo_dir = None
project_dir = None

def load(arg):
    """ Load given class name, raising exception if not previously pickled """

    # Check if file exists to begin with
    fname = "pickle/" + arg + ".pickle"
    if not os.path.exists(fname): raise ValueError

    # Load pickled file as data!
    pickle_file = open(fname, "rb")
    data = pickle.load(pickle_file)
    pickle_file.close()
    return data

def save(*args):
    """ Picklize all given classes """

    # Attempt to serialize our classes (and thus, our data) with pickle
    # NOTE: Must open the files in binary mode ("b")
    pickle_dir = project_dir + "/pickle/"
    for a in args:
        with open("{}{}.pickle".format(pickle_dir, a.__name__), "wb+") as f:
            pickle.dump(a, f)

def extract(repo_name, live = True):
    """ Extract repository data into custom objects """

    # NOTE: For each source file delta, all relevant developers and
    # organizations gain an EA for a particular file, technology, module,
    # subcomponent, etc.
    # NOTE: Expecting all (git) repos to be in a folder at "../../Repos/"

    global repo_dir, project_dir
    epool, fpool = (None, None)

    # We have choice to do new extraction, or to load a previous one
    if not live:

        # Load collection of entities and files
        epool = load("EntityPool")
        fpool = load("FilePool")

    else:

        # Change to code base directory (for git functionality), while also
        # storing the source directory
        repo_dir = base_repo_dir + repo_name
        project_dir = os.getcwd()
        os.chdir(repo_dir)

        # Gather all directory (and subdirectory) files, and then parse them
        # into the proper classes
        print("Scanning code base...")
        file_names = walk_dir(".")
        print("Collected {} source code files in {}".format( \
            len(file_names), repo_dir))
        epool, fpool = parse_git_logs(file_names)

        # Come back to the project, my love!
        os.chdir(project_dir)

    return epool, fpool

def parse_git_logs(file_names):
    """ Parse git change/commit logs from argument list of file names """

    # Initialize our object pools
    epool = EntityPool()
    fpool = FilePool()

    # Vars for remaining time estimation
    i = 1
    l = len(file_names)
    start_time = time.clock()

    print()
    for file_name in file_names[:]:

        # Parse stuff
        parse_git_commit_log(file_name, epool, fpool)

        # Prediction stuff
        # NOTE: We don't take into account the sizes of files
        elapsed = time.clock() - start_time     # s
        avg_time_per_file = elapsed / i         # s
        remaining = l - i
        time_left = remaining * avg_time_per_file
        time_left_min = round((time_left / 60), 2)

        # Display stuff
        restart_line()
        time_left_str = "{} {}".format(time_left_min, "minutes left")
        sys.stdout.write("[{}/{}] {} {}".format(i, l, time_left_str, file_name))
        sys.stdout.flush()

        i += 1

    # Print iteration info
    print()
    print()
    for eid, e in epool.pool.items(): print("\t", len(e.eas), "\t", eid)
    print()
    print("-" * 30)
    print(len(epool.pool), "developers")
    print(len(fpool.pool), "files")
    print("-" * 30)
    print()

    # Save these classes and return them
    save(epool, fpool)
    return epool, fpool

def walk_dir(dir_name):
    """
    Iteratively explore and extract data w/in whole directory structure.
    NOTE: Pervious recursive approach killed stack.
    """

    dir_queue = queue.Queue()
    file_bag = []

    # Walk over current directory
    dir_queue.put(dir_name)
    while not dir_queue.empty():

        curr_dir = dir_queue.get()

        for (dir_path, sub_dir_names, file_names) in os.walk(curr_dir):

            # Add each subdirectory to queue to visit later
            for sub_dir_name in sub_dir_names:
                dir_queue.put(dir_concat(dir_path, sub_dir_name))

            # Put those filenames in the bag! Adding directory structure
            # to name as well
            file_bag.extend([dir_concat(dir_path, x) for x in file_names])

    return file_bag

def dir_concat(dir_pre, dir_post):
    return dir_pre + "/" + dir_post

def parse_and_package(f, l):
    """
    Parse given git delta line by single user, i.e., a line of the form
        "[name]\t[email]\t[commit datetime]\t[num inserted lines] \
        \t[num deleted lines]\t[relative filename]"
    Parse and package up all information given!
    """

    # Tokenize for fields
    fields = l.split("\t")

    # Entity-related
    name = fields[0]
    email = fields[1]

    # Delta-related
    abs_file = f
    # Time format example: "Tue Oct 28 21:33:23 2014 -0400"
    date_time = datetime.strptime(fields[2], "%a %b %d %H:%M:%S %Y %z")
    try:
        num_insert = int(fields[3])
        num_delete = int(fields[4])
    except:
        # "git log --numstat ..." will sometimes give hyphens instead of 0s
        num_insert = 0
        num_delete = 0

    # Package-up
    commit_data = {
        "name": name,
        "email": email,
        "abs_file": abs_file,
        "date_time": date_time,
        "num_insert": num_insert,
        "num_delete": num_delete }

    return commit_data

def create_delta(data):
    """ Simple. From data, create Delta object """

    delta = Delta(
        data["abs_file"],
        data["num_insert"],
        data["num_delete"],
        data["date_time"])

    return delta

def get_entities(data, epool):
    """ Get Entity objects from single delta, making sure they're in the pool """

    # TODO: Add organizational entities

    # Parse entities associated with this single delta
    name = data["name"]
    email = data["email"]

    # Get/create entity
    entity = epool.get(email)
    if entity is None:
        # Add new entity to the entity pool
        entity = Entity(name, email)
        epool.add(entity)

    return [entity]

def parse_git_commit_log(f, epool, fpool):
    """ Parse given file's git commit log """

    # NOTE: Potential loss of information by ignoring merges! Only taking not
    # of changes to master branch

    # Get developer name, email, datetime, number of inserted lines,
    # and the number of deleted lines
    pretty_format = "\"%an\t%ae\t%ad\t\""
    git_commits = ("git log --format={} --no-merges --numstat {} | sed \"/^$/d\"") \
        .format(pretty_format, f)
    output = subprocess.getoutput(git_commits)
    lines = output.split('\n')

    # Instantiate file object from file path and add to file pool
    ffile = File(f)
    fpool.add(ffile)

    # Pair each commit author with commit stats
    pairs = [x + y for x, y in zip(lines[::2], lines[1::2])]
    for p in pairs:

        # Parse commit info
        data = parse_and_package(f, p)

        # Create delta from data
        delta = create_delta(data)

        # Gather list of entities relevant to delta:
        # developers, organizations, etc.
        entities = get_entities(data, epool)

        # Link each entity from delta to a unique EA, which is then linked
        # to the (argument) file
        for entity in entities:

            # Birth of new EA for this entity
            ea = ExperienceAtom(entity, ffile, delta)

            # Double-sided link, where EA is middle of link
            ffile.link(ea)
            entity.link(ea)
