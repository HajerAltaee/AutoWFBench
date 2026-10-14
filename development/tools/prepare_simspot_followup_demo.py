"""Fixture setup only; Sapiens must make the live follow-up decisions through UI."""
from pathlib import Path
import json
import argparse

from development.simspot_ui.state import Store

def main():
    ROOT = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New local fixture/evidence directory")
    args = parser.parse_args()
    OUT = args.output.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    DB = OUT / "demo.sqlite3"
    if DB.exists():
        parser.error("Demo database already exists; preserve it and choose a new output directory")
    source = json.loads((ROOT / "development/simspot_ui/examples/mock-leads.json").read_text())
    store = Store(DB)
    clock = "2026-10-14T10:00:00Z"
    timestamps = {1: "2026-10-11T10:00:00Z", 2: "2026-10-14T08:00:00Z",
                  3: "2026-10-10T10:00:00Z", 4: "2026-10-11T10:00:00Z",
                  5: None, 6: "2026-10-14T08:00:00Z", 7: "2026-10-12T10:00:00Z",
                  8: "2026-10-14T08:00:00Z", 9: None, 10: "2026-10-14T08:00:00Z"}
    roster = []
    for number, row in enumerate(source['leads'], 1):
        matches = [c for c in store.contacts(row['email']) if c['email'] == row['email']]
        c = matches[0] if matches else store.create_contact({k: row[k] for k in ('email','first_name','last_name')})
        ident = c['contact_id']
        store.update(ident, {'job_title':row['job_title'], 'do_not_contact':number == 3})
        context = row['discovery_context']
        if number == 3:
            context = "Do not contact. Retain only this fictional preference; no sensitive customer details."
        store.create_activity(ident,'note',{'body':context,'include_company':False})
        if timestamps[number]:
            body = "Please do not contact me again." if number == 3 else row['fixture_last_customer_message_excerpt']
            store.create_activity(ident,'message',{'source_id':f'followup-demo-{number}-initial','body':body,'received_at':timestamps[number]})
        if number == 4:
            store.create_activity(ident,'task',{'title':'Follow up with Priya about procurement','body':'Ask whether the procurement director can join the evaluation.','due_date':'2026-10-14','include_company':False})
        roster.append({'lead_id':row['lead_id'],'name':row['first_name']+' '+row['last_name'],'email':row['email'],'contact_id':ident,'url':'http://127.0.0.1:8766/#contact/'+ident})
    snapshot={'contacts':store.contacts(),'activities':{c['contact_id']:store.activities(c['contact_id']) for c in store.contacts()}}
    (OUT/'baseline.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
    (OUT/'roster.json').write_text(json.dumps({'evaluation_clock_utc':clock,'leads':roster},indent=2),encoding='utf-8')
    (OUT/'setup-evidence.json').write_text(json.dumps({'setup_method':'Direct local Store fixture setup, NOT Sapiens or UI actions','clock':clock,'contacts':len(snapshot['contacts']),'seeded_pending_tasks':1,'database':str(DB)},indent=2),encoding='utf-8')
    print(json.dumps({'demo_database':str(DB),'contacts':len(snapshot['contacts']),'roster':len(roster),'clock':clock}))


if __name__ == "__main__":
    main()
