from anytree import Node, find, find_by_attr, RenderTree, findall_by_attr
from anytree.importer import JsonImporter, DictImporter
from anytree.exporter import JsonExporter, DictExporter
from anytree.search import findall
from anytree.iterators import PreOrderIter
import json
from typing import Literal
from time import time as now
from pathlib import Path
from flask import Response, request, current_app, abort
from flask.views import MethodView
from slugify import slugify
import os
# from anytree import Node, find, find_by_attr, findall_by_attr, DictImporter, DictExporter

DEBUG = os.uname().nodename != "rockpi-4b"
DELETE_DEBATE_PASSWORD = "simon-says"
DEBATES_SAVE_PATH = Path("debates.json")
DEFS_SAVE_PATH = Path("definitions.json")
# make sure they exist
DEBATES_SAVE_PATH.touch(exist_ok=True)
DEFS_SAVE_PATH.touch(exist_ok=True)

app = current_app()
log = app.logger

# Debates Structure: {argID: rootNode}
# Definitions Structure: {argID: [{"word": "", "definition": ""}, ]}


if DEBUG:
    debates = {'1': Node('premise', id=0, children=[Node('arg1', id=1, children=[])]), slugify('All drugs should be legal'): Node('All drugs should be legal.', id=0, children=[Node('Because theyre tasty', id=1, children=[])])}
    definitions = {'1': [{"word": "from Django", "definition": "def"}], slugify('All drugs should be legal'): []}
else:
    debates = {}
    if DEBATES_SAVE_PATH.exists():
        with open(DEBATES_SAVE_PATH, 'r') as f:
            loaded = json.load(f)
            for argID, tree in loaded.items():
                debates[argID] = DictImporter().import_(tree)

    if DEFS_SAVE_PATH.exists():
        with open(DEFS_SAVE_PATH, 'r') as f:
            definitions = json.load(f)
    else:
        definitions = {}




def _parse_response(request):
    if len(resp := list(request.data.keys())):
        return resp[0]
    else:
        return

def _get_next_id(tree):
    # This should work, actually
    # biggest = Node('', id=-1)
    # for node in PreOrderIter(tree):
    #     if node.id > biggest.id:
    #         biggest = node
    # print("creating new node with id", biggest.id + 1)
    # return biggest.id + 1
    # This is kind of a better solution anyway.
    rtn = round(now() * 10000)
    print("creating node with id", rtn)
    return rtn

def ensure_debate_exists_and_is_valid(func):
    def inner(request, argID, *args, **kwargs):
        global debates, definitions

        argID = slugify(argID)

        if argID not in debates:
            log.error(f"Requested debate with argID `{argID}` does not exist")
            abort(403)
        else:
            # Check for duplicate ids and remove extras if there are any
            nodes = findall_by_attr(debates[argID], id, 'id')
            if len(nodes) > 1:
                for node in nodes[1::-1]:
                    log.warning('Found duplicate nodes, deleting one')
                    nodes[node].parent = None

            rtn = func(request, argID=argID, *args, **kwargs)
            log.debug('Current debate:\n', DictExporter().export(debates[argID]))
            log.debug('Current defs:\n', definitions[argID])
            return rtn
    return inner

def _get_node(argID, id):
    nodes = findall_by_attr(debates[argID], id, 'id')
    if len(nodes):
        return nodes[0]

# path("api/<str:argID>/edit/<int:id>/", views.edit),
#     path("api/<str:argID>/add_sibling/<int:id>/", views.add_sibling),
#     path("api/<str:argID>/add_child/<int:id>/", views.add_child),
#     path("api/<str:argID>/load/", views.load),
#     path("api/<str:argID>/clear/", views.clear),
#     path('api/<str:argID>/delete/<int:id>/', views.delete),
#     path('api/<str:argID>/delete_debate/', views.delete_debate),
#     path('api/<str:argID>/new_debate/', views.new_debate),
#     path('api/<str:argID>/get_debate/', views.get_debate),
#     path('api/<str:argID>/get_whole_debate/', views.get_whole_debate),
#     path('api/<str:argID>/check_exists/', views.check_exists),
#     path('api/get_all_debates/', views.get_all_debates),
#     # Definitions
#     path('api/<str:argID>/get_defs/', views.get_defs),
#     path('api/<str:argID>/clear_defs/', views.clear_defs),
#     path('api/<str:argID>/new_def/', views.new_def),
#     path('api/<str:argID>/edit_def/<int:idx>/<str:which>/', views.edit_def),
#     path('api/<str:argID>/load_defs/', views.load_defs),
# Debates
@app.route('debate/<argID>/edit/<int:id>/', methods=['PUT'])
@ensure_debate_exists_and_is_valid
def edit(argID, id):
    global debates
    node = _get_node(argID, id)
    if not node:
        log.error(f'Invalid edit request given: id: {id}, argID: {argID}')
        abort(400)
    node.name = _parse_response(request)
    return 202

@app.route('debate/<argID>/add_sibling/<int:id>/', methods=['POST'])
@ensure_debate_exists_and_is_valid
def add_sibling(argID, id):
    global debates
    node = _get_node(argID, id)
    if not node:
        log.error(f'Invalid sibling creation request given: id: {id}, argID: {argID}')
        abort(400)
    Node('', parent=node.parent, id=_get_next_id(debates[argID]))
    return 201

@app.route('debate/<argID>/add_child/<int:id>/', methods=['POST'])
@ensure_debate_exists_and_is_valid
def add_child(argID, id):
    global debates
    node = _get_node(argID, id)
    if not node:
        log.error(f'Invalid child creation request given: id: {id}, argID: {argID}')
        abort(400)
    Node('', parent=node, id=_get_next_id(debates[argID]))
    return 201

@app.route('debate/<argID>/load/', methods=['POST'])
@ensure_debate_exists_and_is_valid
def load(argID):
    global debates
    log.debug(f'Loading new debate into debate {argID}')
    debates[argID] = DictImporter().import_(request.data)
    return 201

@app.route('debate/<argID>/clear/', methods=['DELETE'])
@ensure_debate_exists_and_is_valid
def clear(argID):
    global debates
    log.debug(f'Clearing debate {argID}')
    premise = Node('', id=0)
    Node('', id=1, parent=premise)
    debates[argID] = premise
    return 205

@app.route('debate/<argID>/delete/<int:id>/', methods=['DELETE'])
@ensure_debate_exists_and_is_valid
def delete(argID, id):
    global debates
    node = _get_node(argID, id)
    if not node:
        log.error(f'Invalid delete request given. argID: {argID}')
        abort(400)
    else:
        node.parent = None
    return 204

@app.route('debate/new_debate/', methods=['POST'])
def new_debate(argID):
    global debates, definitions
    argID = slugify(argID)
    if argID in debates:
        log.error(f'New debate requested, but it already exists: {argID}')
        abort(303)
    else:
        premise = Node('', id=0)
        Node('', id=1, parent=premise)
        debates[argID] = premise
        definitions[argID] = []
    log.debug(f'New debate created: {argID}')
    return 201

@app.route('debate/<argID>/get_debate/', methods=['GET'])
@ensure_debate_exists_and_is_valid
def get_debate(argID):
    global debates
    return JsonExporter().export(debates[argID])

@app.route('debate/check_exists/', methods=['GET'])
def check_exists(argID):
    global debates
    return slugify(argID) in debates

@app.route('debate/get_all_debates/', methods=['GET'])
def get_all_debates(request):
    global debates
    return json.dumps([[key, premise.name] for key, premise in debates.items()])

@app.route('debate/<argID>/get_whole_debate/', methods=['GET'])
@ensure_debate_exists_and_is_valid
def get_whole_debate(argID):
    global debates, definitions
    return json.dumps([DictExporter().export(debates[argID]), definitions[argID]])

@app.route('debate/<argID>/delete_debate/', methods=['DELETE'])
@ensure_debate_exists_and_is_valid
def delete_debate(argID):
    global debates, definitions
    if request.data == DELETE_DEBATE_PASSWORD and argID in debates:
        del debates[argID]
        del definitions[argID]
        log.debug(f'Deleted debate: {argID}')
        return 202
    else:
        if request.data != DELETE_DEBATE_PASSWORD:
            log.error(f'Invalid password attempt: `{request.data}`')
        else:
            log.error(f'Cant delete debate, it doesnt exist: {argID}')
        return 406


# Definitions
@app.route('debate/<argID>/get_defs/', methods=['GET'])
@ensure_debate_exists_and_is_valid
def get_defs(argID):
    global definitions
    return json.dumps(definitions[argID])

@app.route('debate/<argID>/clear_defs/', methods=['DELETE'])
@ensure_debate_exists_and_is_valid
def clear_defs(argID):
    global definitions
    log.debug(f'Clearing definitions: {argID}')
    definitions[argID] = []
    return 205

@app.route('debate/<argID>/new_def/', methods=['POST'])
@ensure_debate_exists_and_is_valid
def new_def(argID):
    global definitions
    definitions[argID].append({'word': '', 'definition': ''})
    return 201

@app.route('debate/<argID>/edit_def/<int:idx>/<str:which>/', methods=['PUT'])
@ensure_debate_exists_and_is_valid
def edit_def(argID, idx, which:Literal['word', 'definition']):
    global definitions
    definitions[argID][idx][which] = _parse_response(request)
    return 202

@app.route('debate/<argID>/load_defs/', methods=['POST'])
@ensure_debate_exists_and_is_valid
def load_defs(argID):
    global definitions
    definitions[argID] = request.data
    log.debug(f'Definitions added to debate {argID}')
    return 201

@app.route('save_all/', methods=['POST'])
def save_all():
    DEBATES_SAVE_PATH.write_text(json.dumps({argID: DictExporter().export(tree) for argID, tree in debates.items()}))
    DEFS_SAVE_PATH.write_text(json.dumps(definitions))

    log.debug("Saved debates!")

    return 204