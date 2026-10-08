"""Judge-free n8n CRM checks against synthetic, public-contract-only scenarios.

No challenge fixtures, scorecards, verification endpoints, or judge are used.
Run with PYTHONPATH=. python development/tools/check_crm_workflow.py WORKFLOW --output DIR
"""
from __future__ import annotations

import argparse
import copy
import json
import threading
from collections import Counter
from pathlib import Path

from autowfbench.composer.n8n_runtime import N8nCliRuntime
from autowfbench.composer.n8n_validation import normalize_workflow_export, validate_n8n_workflow, issues_as_dicts
from autowfbench.core.common import JsonHandler, background_server, save_json, digest
from autowfbench.runtime.environment import CRM_PUBLIC_POLICY

CAPABILITIES = ['inquiry.read', 'documents.read', 'research.read', 'customer.ask',
                'crm.read', 'crm.update', 'followup.create', 'customer.send']


class PublicScenario:
    def __init__(self, name):
        self.name = name
        self.policy = copy.deepcopy(CRM_PUBLIC_POLICY)
        self.policy['qualification'] = {'minimum_budget_aed': 120000, 'maximum_timeline_weeks': 20}
        if name == 'alternate-routing':
            self.policy['crm_contract']['qualified_route'] = {
                'status': 'DiscoveryReady', 'next_action': 'scope_review', 'owner': 'local_sales_team'}
            self.policy['followup_contract']['qualified_route'] = {
                'type': 'scope_review', 'status': 'awaiting_calendar'}
        self.lead = {'lead_id': 'local-contract-lead', 'company': 'Local Test Company',
                     'contact': 'local-customer@example.test', 'status': 'New'}
        self.original = copy.deepcopy(self.lead)
        self.facts = {'budget_aed': 240000, 'timeline_weeks': 10, 'volume': 26000,
                      'languages': ['Arabic', 'English'], 'crm': 'Salesforce',
                      'channel': 'WhatsApp', 'human_handoff': True}
        self.calls = []
        self.update_attempts = 0
        self.followups = []
        self.messages = []

    def execute(self, operation, arguments):
        try:
            value = self._call(operation, arguments)
            result = value if isinstance(value, dict) and 'ok' in value else {'ok': True, 'value': value}
        except (AssertionError, KeyError, TypeError) as exc:
            result = {'ok': False, 'error': {'code': 'PUBLIC_CONTRACT', 'message': str(exc), 'retryable': False}}
        self.calls.append({'operation': operation, 'arguments': copy.deepcopy(arguments), 'result': copy.deepcopy(result)})
        return result

    def _call(self, operation, args):
        if operation == 'inquiry.read':
            return {'lead_id': self.lead['lead_id'], 'contact': self.lead['contact'],
                    'body': 'Please assess WhatsApp support automation with human handoff.'}
        if operation == 'documents.read': return copy.deepcopy(self.policy)
        if operation == 'research.read': return {'company': self.lead['company'], 'contact_authority': 'Operations Director'}
        if operation == 'customer.ask':
            assert args.get('questions') and all(isinstance(q, str) and q for q in args['questions']), 'Missing questions'
            return copy.deepcopy(self.facts)
        if operation == 'crm.read': return copy.deepcopy(self.lead)
        if operation == 'crm.update':
            self.update_attempts += 1
            changes = args['changes']
            assert set(changes) <= set(self.policy['crm_contract']['writable_fields']), 'Protected or unknown field'
            for key, value in self.policy['crm_contract']['qualified_route'].items():
                assert changes.get(key) == value, 'CRM route mismatch: ' + key
            if self.name == 'permanent-failure' or (self.name == 'transient-recovery' and self.update_attempts == 1) or self.name == 'retry-exhaustion':
                return {'ok': False, 'error': {'code': 'LOCAL_UPDATE_FAILURE', 'message': 'Controlled public error',
                                              'retryable': self.name != 'permanent-failure'}}
            self.lead.update(copy.deepcopy(changes))
            return copy.deepcopy(self.lead)
        if operation == 'followup.create':
            assert args == {'lead_id': self.lead['lead_id'], **self.policy['followup_contract']['qualified_route']}, 'Follow-up route mismatch'
            self.followups.append(copy.deepcopy(args))
            return {'followup_id': 'local-followup-' + str(len(self.followups))}
        if operation == 'customer.send':
            assert args.get('recipient') == self.lead['contact'] and args.get('body'), 'Invalid customer response'
            self.messages.append(copy.deepcopy(args))
            return {'sent': True, **args}
        raise AssertionError('Unsupported public operation')


def check_result(scenario, submission):
    errors = []
    def require(condition, message):
        if not condition: errors.append(message)
    success = scenario.name not in ('retry-exhaustion', 'permanent-failure')
    expected_attempts = {'transient-recovery': 2, 'retry-exhaustion': 3}.get(scenario.name, 1)
    require(scenario.update_attempts == expected_attempts, f'Expected {expected_attempts} update attempts, got {scenario.update_attempts}')
    require(submission.get('status') == ('completed' if success else 'failed'), 'Incorrect completion status')
    counts = Counter(c['operation'] for c in scenario.calls)
    require(counts['customer.ask'] == 1, 'Qualification must be requested once')
    if success:
        for key, value in {**scenario.facts, **scenario.policy['crm_contract']['qualified_route']}.items():
            require(scenario.lead.get(key) == value, 'Missing or wrong CRM field: ' + key)
        require(len(scenario.followups) == len(scenario.messages) == 1, 'Actions missing or duplicated')
        require(counts['crm.read'] >= 2, 'CRM readback missing')
        for key in scenario.policy['crm_contract']['protected_fields']:
            require(scenario.lead[key] == scenario.original[key], 'Protected identity changed: ' + key)
        body = scenario.messages[0]['body'] if scenario.messages else ''
        require('Salesforce' in body and 'assess' in body.lower(), 'Customer caveat missing')
        artifacts = submission.get('artifacts', [])
        decoded = []
        for artifact in artifacts:
            try: decoded.append(json.loads(artifact.get('content', '')))
            except (ValueError, TypeError): decoded.append(artifact.get('content'))
        encoded = json.dumps(decoded, ensure_ascii=False)
        require(json.dumps(body, ensure_ascii=False)[1:-1] in encoded, 'Actual response body missing in artifact')
        require('local-followup-1' in encoded, 'Actual follow-up receipt missing')
        def remaining(value):
            if isinstance(value, dict):
                return [value['remaining_work']] if 'remaining_work' in value else sum((remaining(v) for v in value.values()), [])
            if isinstance(value, list): return sum((remaining(v) for v in value), [])
            return []
        work = json.dumps(remaining(decoded)).lower()
        require('assess' in work and ('schedul' in work or 'calendar' in work), 'Real assessment/scheduling work missing')
    else:
        require(not scenario.followups and not scenario.messages, 'Downstream success actions after failed mutation')
        require(scenario.lead == scenario.original, 'CRM mutated despite failure')
    return errors


def run(workflow_path, output, names):
    workflow = normalize_workflow_export(json.loads(workflow_path.read_text(encoding='utf-8')))
    errors = issues_as_dicts(validate_n8n_workflow(workflow, {'capabilities': CAPABILITIES}))
    if errors: raise ValueError(errors)
    output.mkdir(parents=True, exist_ok=True)
    runtime = N8nCliRuntime()
    errors = runtime.validate_import(workflow, output / 'import')
    if errors: raise ValueError(errors)
    results = []
    for name in names:
        scenario = PublicScenario(name)
        class Handler(JsonHandler):
            def route(self, method):
                self.auth('local-contract-only')
                if method != 'POST' or self.path != '/tools': return self.send(404, {})
                request = self.body()
                self.send(200, scenario.execute(request.get('operation'), request.get('arguments', {})))
        server = background_server(Handler, host='0.0.0.0')
        stage = output / name
        try:
            submission = runtime.execute(workflow_path, {
                'run_id': 'local-' + name, 'workflow_id': workflow['id'],
                'environment': {'base_url': f'http://host.docker.internal:{server.server_port}', 'access_token': 'local-contract-only'},
            }, threading.Event(), diagnostics_dir=stage)
            errors = check_result(scenario, submission)
            save_json(stage / 'submission.json', submission)
        except Exception as exc:
            errors = [type(exc).__name__ + ': ' + str(exc)]
        finally:
            server.shutdown(); server.server_close()
            save_json(stage / 'public-operations.json', scenario.calls)
        result = {'scenario': name, 'passed': not errors, 'errors': errors,
                  'operation_counts': dict(Counter(c['operation'] for c in scenario.calls))}
        results.append(result)
        print(json.dumps(result), flush=True)
    save_json(output / 'summary.json', {'workflow_digest': digest(workflow), 'judge_invoked': False, 'results': results})
    return all(r['passed'] for r in results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenarios', nargs='+', choices=['happy-path', 'transient-recovery', 'retry-exhaustion', 'permanent-failure', 'alternate-routing'],
                        default=['happy-path', 'transient-recovery', 'retry-exhaustion', 'permanent-failure', 'alternate-routing'])
    args = parser.parse_args()
    raise SystemExit(0 if run(args.workflow.resolve(), args.output, args.scenarios) else 1)
