import copy
import unittest
from unittest.mock import patch
from workbrain.collect import collect
from workbrain.config import DEFAULT


class ContractTests(unittest.TestCase):
    def test_shared_board_contract_includes_descendants_only(self):
        config = copy.deepcopy(DEFAULT)
        config['projects'] = [{'id': 'one', 'name': 'One', 'asana_project': 'board', 'asana_contract_tag': 'contract-one'},
                              {'id': 'two', 'name': 'Two', 'asana_project': 'board', 'asana_contract_tag': 'contract-two'}]
        config['providers'] = {'asana': {'credential': {'env': 'FIXTURE_TOKEN'}}}
        tasks = [{'gid': 'a', 'tags': [{'gid': 'contract-one'}]}, {'gid': 'b', 'parent': {'gid': 'a'}},
                 {'gid': 'c', 'tags': [{'gid': 'contract-two'}]}]
        with patch('workbrain.collect.credential', return_value='synthetic'), patch('workbrain.collect.task_tree', return_value=tasks):
            snapshot = collect(config, factory=lambda *args: object())
        self.assertEqual([[t['gid'] for t in p['tasks']] for p in snapshot['projects']], [['a', 'b'], ['c']])

    def test_pausing_one_contract_does_not_hide_other_board_assignments(self):
        config = copy.deepcopy(DEFAULT)
        config['projects'] = [{'id': 'paused', 'name': 'Paused', 'status': 'paused',
                               'asana_project': 'shared-board', 'asana_contract_tag': 'contract-one'}]
        config['owner'] = {'asana_user': 'me', 'asana_workspace': 'workspace'}
        config['providers'] = {'asana': {'credential': {'env': 'FIXTURE_TOKEN'}}}
        class Client:
            def all(self, *args):
                return [{'gid': 'child', 'parent': {'gid': 'parent'}},
                        {'gid': 'active', 'projects': [{'gid': 'shared-board'}], 'tags': [{'gid': 'contract-two'}]}]
            def one(self, *args):
                return {'gid': 'parent', 'tags': [{'gid': 'contract-one'}]}
        with patch('workbrain.collect.credential', return_value='synthetic'):
            snapshot = collect(config, factory=lambda *args: Client())
        self.assertEqual([t['gid'] for t in snapshot['assignments']], ['active'])

    def test_project_specific_gitlab_credentials_do_not_fall_back(self):
        config = copy.deepcopy(DEFAULT)
        config['projects'] = [{'id': 'one', 'name': 'One', 'gitlab_projects': ['group/one'], 'gitlab_provider': 'restricted'}]
        config['providers'] = {'restricted': {'credential': {'env': 'RESTRICTED_TOKEN'}},
                               'gitlab': {'credential': {'env': 'UNRELATED_TOKEN'}}}
        class Client:
            def one(self, *args):
                return {'path_with_namespace': 'group/one', 'web_url': 'https://gitlab.example.com/group/one'}
            def all(self, *args):
                return []
        calls = []
        def factory(base, token, kind):
            calls.append((base, token, kind)); return Client()
        with patch('workbrain.collect.credential', return_value='synthetic') as read:
            collect(config, factory=factory)
        read.assert_called_once_with({'env': 'RESTRICTED_TOKEN'})
        self.assertEqual(calls[0][2], 'gitlab')
