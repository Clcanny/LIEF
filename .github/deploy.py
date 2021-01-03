#!/usr/bin/env python3
import sys
import os
import re
import logging
import pathlib
import subprocess
import shutil
from mako.template import Template
from enum import Enum, auto

class CI(Enum):
    UNKNOWN        = auto()
    TRAVIS         = auto()
    APPVEYOR       = auto()
    GITLAB_CI      = auto()
    CIRCLE_CI      = auto()
    GITHUB_ACTIONS = auto()
    AZURE          = auto()
    LOCAL          = auto()

def pretty_ci_name(ci):
    return str(ci).split(".")[-1].replace("_", "-").lower()

def is_pr(ci):
    if ci == CI.TRAVIS:
        cond1 = os.getenv("TRAVIS_EVENT_TYPE", "pull_request") == "pull_request"
        cond2 = not os.getenv("TRAVIS_REPO_SLUG", "").startswith("lief-project/")
        return cond1 or cond2
    elif ci == CI.APPVEYOR:
        logger.info("%s - %s", os.getenv("APPVEYOR_PULL_REQUEST_NUMBER", -1), os.getenv("APPVEYOR_REPO_NAME", ""))
        pr_number = os.getenv("APPVEYOR_PULL_REQUEST_NUMBER", "")
        cond1 = len(pr_number) != 0 and int(pr_number) >= 0
        cond2 = not os.getenv("APPVEYOR_REPO_NAME", "").startswith("lief-project/")
        return cond1 or cond2
    elif ci == CI.CIRCLE_CI:
        cond1 = int(os.getenv("CIRCLE_PR_NUMBER", -1)) >= 0
        cond2 = os.getenv("CIRCLE_PROJECT_USERNAME", "") != "lief-project"
        return cond1 or cond2
    elif ci == CI.GITHUB_ACTIONS:
        cond1 = os.getenv("GITHUB_HEAD_REF", "") != ""
        cond2 = not os.getenv("GITHUB_REPOSITORY", "").startswith("lief-project/")
        return cond1 or cond2
    elif ci == CI.LOCAL:
        return False
    return True

def get_branch(ci):
    if ci == CI.TRAVIS:
        return os.getenv("TRAVIS_BRANCH")
    elif ci == CI.APPVEYOR:
        return os.getenv("APPVEYOR_REPO_BRANCH")
    elif ci == CI.CIRCLE_CI:
        return os.getenv("CIRCLE_BRANCH")
    elif ci == CI.GITHUB_ACTIONS:
        return os.getenv("GITHUB_REF").replace("refs/heads/", "")
    elif ci == CI.LOCAL:
        return os.getenv("CI_BRANCH")
    return None

def get_ci_workdir(ci):
    if ci == CI.CIRCLE_CI:
        return os.getenv("CIRCLE_WORKING_DIRECTORY")
    elif ci == CI.TRAVIS:
        return os.getenv("TRAVIS_BUILD_DIR")
    elif ci == CI.APPVEYOR:
        return  os.getenv("APPVEYOR_BUILD_FOLDER")
    elif ci == CI.GITHUB_ACTIONS:
        return os.getenv("GITHUB_WORKSPACE")
    elif ci == CI.LOCAL:
        return os.getenv("CI_WORKING_DIR")
    else:
        logger.critical("Unsupported CI to resolve working directory")
        sys.exit(1)



LOG_LEVEL = logging.DEBUG

logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))
logging.getLogger().setLevel(LOG_LEVEL)
logger = logging.getLogger(__name__)

CURRENT_CI = CI.UNKNOWN

# Detect CI
# ===========================================
if os.getenv("TRAVIS", None) is not None:
    CURRENT_CI = CI.TRAVIS
elif os.getenv("APPVEYOR", None) is not None:
    CURRENT_CI = CI.APPVEYOR
elif os.getenv("GITHUB_ACTIONS", None) is not None:
    CURRENT_CI = CI.GITHUB_ACTIONS
elif os.getenv("GITLAB_CI", None) is not None:
    CURRENT_CI = CI.GITLAB_CI
elif os.getenv("CI_LOCAL", "") == "true":
    CURRENT_CI = CI.LOCAL
else:
    print("Can't detect CI!", file=sys.stderr)
    sys.exit(1)
# TODO(romain): Azure

logger.info("CI: %s", pretty_ci_name(CURRENT_CI))

ALLOWED_BRANCHES = {"master", "deploy", "devel", "enhancement/cpack"}
BRANCH_NAME = get_branch(CURRENT_CI)
logger.info("Branch: %s", BRANCH_NAME)
if BRANCH_NAME not in ALLOWED_BRANCHES:
    logger.info("Skip deployment for branch '%s'", BRANCH_NAME)
    sys.exit(0)

if is_pr(CURRENT_CI):
    logger.info("Skip pull request")
    sys.exit(0)

CURRENTDIR = pathlib.Path(__file__).resolve().parent
REPODIR    = CURRENTDIR.parent

DEPLOY_KEY = os.getenv("LIEF_AUTOMATIC_BUILDS_KEY", None)
DEPLOY_IV  = os.getenv("LIEF_AUTOMATIC_BUILDS_IV", None)

if DEPLOY_KEY is None or len(DEPLOY_KEY) == 0:
    print("Deploy key is not set!", file=sys.stderr)
    sys.exit(1)

if DEPLOY_IV is None or len(DEPLOY_IV) == 0:
    print("Deploy IV is not set!", file=sys.stderr)
    sys.exit(1)

GIT_USER  = "lief-{}-ci".format(pretty_ci_name(CURRENT_CI))
GIT_EMAIL = "lief@quarkslab.com"

CI_CWD = pathlib.Path(get_ci_workdir(CURRENT_CI))

if CI_CWD is None:
    logger.debug("Can't resolve CI working dir")
    sys.exit(1)

LIEF_PACKAGE_REPO     = "https://github.com/lief-project/packages.git"
LIEF_PACKAGE_DIR      = REPODIR / "deploy-packages"
LIEF_PACKAGE_SSH_REPO = "git@github.com:lief-project/packages.git"
SDK_PACKAGE_DIR       = LIEF_PACKAGE_DIR / "sdk"
PYPI_PACKAGE_DIR      = LIEF_PACKAGE_DIR / "lief"
DIST_DIR              = REPODIR / "dist"
BUILD_DIR             = REPODIR / "build"


logger.debug("Working directory: %s", CI_CWD)

SSH_DIR     = pathlib.Path("~/.ssh").expanduser().resolve()
PYTHON      = shutil.which("python")
GIT         = shutil.which("git")
TAR         = shutil.which("tar")
OPENSSL     = shutil.which("openssl")
MV          = shutil.which("mv")
RM          = shutil.which("rm")
SSH_AGENT   = shutil.which("ssh-agent")
SSH_ADD     = shutil.which("ssh-add")
SSH_KEYSCAN = shutil.which("ssh-keyscan")

if DEPLOY_KEY is None:
    print("Deploy key is not set!", file=sys.stderr)
    sys.exit(1)

if DEPLOY_IV is None:
    print("Deploy IV is not set!", file=sys.stderr)
    sys.exit(1)


#####################
# Clone package repo
#####################
target_branch = "gh-pages"
if not LIEF_PACKAGE_DIR.is_dir():
    cmd = "{} clone --branch={} -j8 --single-branch {} {}".format(GIT, target_branch, LIEF_PACKAGE_REPO, LIEF_PACKAGE_DIR)
    p = subprocess.Popen(cmd, shell=True, cwd=REPODIR, stderr=subprocess.STDOUT)
    p.wait()

    if p.returncode:
        sys.exit(1)

SDK_PACKAGE_DIR.mkdir(exist_ok=True)
PYPI_PACKAGE_DIR.mkdir(exist_ok=True)

logger.info("CI: %s - %s", GIT_USER, GIT_EMAIL)
cmds = [
    #"chmod 700 .git",
    "{} config user.name '{}'".format(GIT, GIT_USER),
    "{} config user.email '{}'".format(GIT, GIT_EMAIL),
    "{} reset --soft root".format(GIT),
    "{} ls-files -v".format(GIT),
]

for cmd in cmds:
    p = subprocess.Popen(cmd, shell=True, cwd=LIEF_PACKAGE_DIR, stderr=subprocess.STDOUT)
    p.wait()

    if p.returncode:
        sys.exit(1)

for file in DIST_DIR.glob("*.whl"):
    logger.debug("Copying '%s' to '%s'", file.as_posix(), PYPI_PACKAGE_DIR.as_posix())
    shutil.copy(file.as_posix(), PYPI_PACKAGE_DIR.as_posix())

for file in BUILD_DIR.glob("*.zip"):
    logger.debug("Copying '%s' to '%s'", file.as_posix(), SDK_PACKAGE_DIR.as_posix())
    shutil.copy(file.as_posix(), SDK_PACKAGE_DIR.as_posix())

for file in BUILD_DIR.glob("*.tar.gz"):
    logger.debug("Copying '%s' to '%s'", file.as_posix(), SDK_PACKAGE_DIR.as_posix())
    shutil.copy(file.as_posix(), SDK_PACKAGE_DIR.as_posix())


INDEX_TEMPLATE = r"""
<html>
<title>Links for lief</title>
<body>
<h1>Links for lief</h1>
% for name in names:
    <a href="${base_url}/${base}/${name}">${name}</a><br />
% endfor
</body>
</html>
"""

EXCLUDED = ['index.html', '.gitkeep']
BASE_URL = "https://lief-project.github.io"

fnames = [fname for fname in sorted(f.name for f in PYPI_PACKAGE_DIR.iterdir() if f.is_file() and f.name not in EXCLUDED)]
html = Template(INDEX_TEMPLATE).render(names=fnames, base_url=BASE_URL, base="packages/lief")
with open((PYPI_PACKAGE_DIR / "index.html").as_posix(), "w") as f:
    f.write(html)


fnames = [fname for fname in sorted(f.name for f in SDK_PACKAGE_DIR.iterdir() if f.is_file() and f.name not in EXCLUDED)]
html = Template(INDEX_TEMPLATE).render(names=fnames, base_url=BASE_URL, base="packages/sdk")
with open((SDK_PACKAGE_DIR / "index.html").as_posix(), "w") as f:
    f.write(html)



if not SSH_DIR.is_dir():
    SSH_DIR.mkdir(mode=0o700)

#fix_ssh_perms()
deploy_key_path = (REPODIR / ".github" / "deploy-key.enc").as_posix()
output_key_path = (REPODIR / ".git" / "deploy-key")
cmd = "{} aes-256-cbc -K {} -iv {} -in {} -out {} -d".format(
        OPENSSL, DEPLOY_KEY, DEPLOY_IV, deploy_key_path, output_key_path.as_posix())

kwargs = {
    'shell': True,
    'cwd':   REPODIR,
    'stdout': subprocess.DEVNULL,
    'stderr': subprocess.DEVNULL,
}

p = subprocess.Popen(cmd, **kwargs)
p.wait()

if p.returncode:
    sys.exit(1)

output_key_path.chmod(0o600)
print(output_key_path)

process = subprocess.run(SSH_AGENT, stdout=subprocess.PIPE, universal_newlines=True, stderr=subprocess.STDOUT)
OUTPUT_PATTERN = re.compile(r'SSH_AUTH_SOCK=(?P<socket>[^;]+).*SSH_AGENT_PID=(?P<pid>\d+)', re.MULTILINE | re.DOTALL)
match = OUTPUT_PATTERN.search(process.stdout)
if match is None:
    logger.error("Can't start ssh-agent")
    sys.exit(1)

agent_data = match.groupdict()
logger.info(f'ssh agent data: {agent_data!s}')
logger.info('Exporting ssh agent environment variables' )

os.environ['SSH_AUTH_SOCK'] = agent_data['socket']
os.environ['SSH_AGENT_PID'] = agent_data['pid']

process = subprocess.run([SSH_ADD, output_key_path], stderr=subprocess.STDOUT)
if process.returncode != 0:
    raise Exception(f'Failed to add the key: {output_key_path}')
known_hosts = (SSH_DIR / "known_hosts").as_posix()
cmd = "{} -H github.com >> {}".format(SSH_KEYSCAN, known_hosts)

kwargs = {
    'shell':  True,
    'cwd':    REPODIR,
    'stderr': subprocess.STDOUT,
}

p = subprocess.Popen(cmd, **kwargs)
p.wait()

if p.returncode:
    sys.exit(1)


cmds = [
    #f"{GIT} diff --cached --exit-code --quiet",
    #"chown -R 1000:1000 *",
    "{} add .".format(GIT),
    "{} commit -m 'Automatic build'".format(GIT),
    "{} ls-files -v".format(GIT),
    #f"{GIT} log --pretty=fuller",
]

for cmd in cmds:
    logger.info("Running %s", cmd)
    p = subprocess.Popen(cmd, shell=True, cwd=LIEF_PACKAGE_DIR, stderr=subprocess.STDOUT)
    p.wait()

    if p.returncode:
        logger.error("Error while running %s", cmd)
        sys.exit(1)

for i in range(10):
    p = subprocess.Popen("{} push --force {} {}".format(GIT, LIEF_PACKAGE_SSH_REPO, target_branch),
            shell=True, cwd=LIEF_PACKAGE_DIR, stderr=subprocess.STDOUT)
    p.wait()

    if p.returncode == 0:
        break

    cmds = [
        "{} branch -a -v".format(GIT),
        "{} fetch -v origin {}".format(GIT, target_branch),
        "{} branch -a -v".format(GIT),
        "{} rebase -s recursive -X theirs FETCH_HEAD".format(GIT),
        "{} branch -a -v".format(GIT),
    ]
    for c in cmds:
        p = subprocess.Popen(c, shell=True, cwd=LIEF_PACKAGE_DIR, stderr=subprocess.STDOUT)
        p.wait()
else:
    logger.critical("Can't push file on %s -> %s", LIEF_PACKAGE_SSH_REPO, target_branch)
    sys.exit(1)


output_key_path.unlink()
print("ok")

