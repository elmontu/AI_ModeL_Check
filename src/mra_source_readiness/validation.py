"""Offline Phase 7A source-readiness checks; no scientific evaluator is imported."""
from __future__ import annotations
import csv,hashlib,io,json,re
from decimal import Decimal
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone

SCHEMA='mra-source-readiness/1.0'
DOMAINS={'moh','mas','msf'}
class ReadinessError(ValueError): pass

def strict_json(raw):
 def pairs(items):
  result={}
  for k,v in items:
   if k in result:raise ReadinessError('Duplicate JSON key: '+k)
   result[k]=v
  return result
 try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ReadinessError('Nonfinite JSON')))
 except (ValueError,TypeError) as e:raise ReadinessError(str(e)) from e

def sha(raw):return hashlib.sha256(raw).hexdigest()

def bound_path(root,name):
 if not isinstance(name,str) or '\\' in name:raise ReadinessError('Use relative POSIX paths')
 p=PurePosixPath(name)
 if p.is_absolute() or any(x in ('..','') for x in p.parts) or ':' in name:raise ReadinessError('Unsafe evidence path')
 candidate=root.joinpath(*p.parts)
 for entry in (candidate,*candidate.parents):
  if entry==root.parent:break
  if entry.is_symlink() or getattr(entry.lstat(),'st_file_attributes',0)&0x400:raise ReadinessError('Redirected evidence path')
 if not candidate.resolve(strict=True).is_relative_to(root.resolve(strict=True)):raise ReadinessError('Evidence outside repository')
 return candidate

def checked_csv(text):
 matrix=list(csv.reader(io.StringIO(text)))
 if not matrix:raise ReadinessError('Empty CSV')
 header=matrix[0]
 if len(set(header))!=len(header) or any(not x for x in header):raise ReadinessError('Duplicate or blank CSV header')
 if any(len(r)!=len(header) for r in matrix[1:] if r):raise ReadinessError('Malformed CSV width')
 return [dict(zip(header,r)) for r in matrix[1:] if r]

def csv_profile(raw,domain):
 text=raw.decode('utf-8-sig')
 if domain=='mas' and text.startswith('"MSB I.17'):
  table=mas_archive_rows(raw)
  months={name:i for i,name in enumerate(('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'),1)}
  normalized=[]
  for r in table:
   period=r.get('PERIOD','')
   if not re.fullmatch(r'\d{4} [A-Z][a-z]{2}',period):continue
   y,m=period.split();normalized.append({'month':f'{y}-{months[m]:02d}','total_billings':r['S$ MILLION - TOTAL CARD BILLINGS'],'rollover_balance':r['S$ MILLION - ROLLOVER BALANCE ^']})
  rows=normalized
 else:rows=checked_csv(text)
 if not rows:raise ReadinessError('Empty CSV')
 if domain=='mas':
  periods=[r['month'] for r in rows]
  if len(set(periods))!=len(periods):raise ReadinessError('Duplicate MAS month')
  for r in rows:
   if not re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])',r['month']):raise ReadinessError('Invalid monthly key')
   for k,v in r.items():
    if k!='month' and (not v or not re.fullmatch(r'\d+(?:\.\d+)?',v)):raise ReadinessError('Invalid MAS count/value')
  indices=[int(p[:4])*12+int(p[5:])-1 for p in periods]
  if sorted(indices)!=list(range(min(indices),max(indices)+1)):raise ReadinessError('Missing MAS month')
  return {'raw_rows':len(rows),'aggregate_cells':len(rows),'start':min(periods),'end':max(periods),'series_count':1,'three_period_eligible':max(0,len(rows)-2)}
 if domain=='msf':
  periods=[k for k in rows[0] if k!='DataSeries']
  if any(not re.fullmatch(r'\d{4}',p) for p in periods):raise ReadinessError('Invalid MSF year')
  if len({r['DataSeries'] for r in rows})!=len(rows):raise ReadinessError('Duplicate MSF series')
  for r in rows:
   if any(not re.fullmatch(r'\d+',r[p]) for p in periods):raise ReadinessError('Invalid MSF household cell')
  return {'raw_rows':len(rows),'aggregate_cells':len(rows)*len(periods),'start':min(periods),'end':max(periods),'series_count':len(rows),'one_lag_eligible':len(rows)*sum(str(int(p)-1) in periods for p in periods),'three_period_eligible':len(rows)*sum(str(int(p)-1) in periods and str(int(p)-2) in periods for p in periods)}
 # Keep publisher epidemiological labels literal; never convert to ISO week.
 fields=set(rows[0]); time_key=next((k for k in ('epi_week','epiweek') if k in fields),None)
 disease_key=next((k for k in ('disease','diseases') if k in fields),None)
 value_key=next((k for k in ('no._of_cases','no_of_cases','number_of_cases','cases') if k in fields),None)
 if not all((time_key,disease_key,value_key)):raise ReadinessError('Unexpected MOH schema: '+repr(fields))
 keys=[(r[time_key],r[disease_key]) for r in rows]
 if len(set(keys))!=len(keys):raise ReadinessError('Duplicate MOH disease week')
 for r in rows:
  if not re.fullmatch(r'\d{4}-W(?:0[1-9]|[1-4][0-9]|5[0-3])',r[time_key]):raise ReadinessError('Invalid MOH publisher week')
  if r[time_key].endswith('W53') and r[time_key][:4] not in ('2014','2020'):raise ReadinessError('MOH week53 outside pinned publisher calendar')
  if not re.fullmatch(r'\d+',r[value_key]):raise ReadinessError('Invalid MOH notification count')
 periods=[r[time_key] for r in rows]
 calendar=[f'{y}-W{week:02d}' for y in range(int(min(periods)[:4]),int(max(periods)[:4])+1) for week in range(1,54 if y in (2014,2020) else 53)];positions={p:i for i,p in enumerate(calendar)};keyset=set(keys)
 eligible=sum(i>=2 and (calendar[i-1],series) in keyset and (calendar[i-2],series) in keyset for period,series in keys for i in [positions[period]])
 return {'raw_rows':len(rows),'aggregate_cells':len(rows),'start':min(periods),'end':max(periods),'series_count':len({r[disease_key] for r in rows}),'three_period_eligible':eligible}

def require_as_of_feature(feature,cutoff):
 """A scheduled date or a current revised file cannot prove historical availability."""
 try:
  released=datetime.fromisoformat(feature['published_at'].replace('Z','+00:00'))
  limit=datetime.fromisoformat(cutoff.replace('Z','+00:00'))
 except (KeyError,ValueError,AttributeError) as e:raise ReadinessError('Missing actual availability timestamp') from e
 if released.tzinfo is None or limit.tzinfo is None:raise ReadinessError('Timezone required')
 if released>limit:raise ReadinessError('Feature unavailable at forecast cutoff')
 if not isinstance(feature.get('official_vintage_sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',feature['official_vintage_sha256']) or feature.get('first_publication_bytes_verified') is not True:raise ReadinessError('Historical source vintage unresolved')
 return True

def validate_manifest(root,manifest):
 root=Path(root)
 if manifest.get('schema')!=SCHEMA or manifest.get('phase')!='7A':raise ReadinessError('Unsupported readiness schema/phase')
 if manifest.get('benchmark_executed') is not False or manifest.get('authorization_effect')!='none':raise ReadinessError('Audit cannot execute or authorize a benchmark')
 if set(manifest['tasks'])!=DOMAINS:raise ReadinessError('All three domains are mandatory')
 paths=set(); captured={}
 for a in manifest['artifacts']:
  if a['path'] in paths:raise ReadinessError('Duplicate evidence binding')
  paths.add(a['path']);raw=bound_path(root,a['path']).read_bytes()
  if sha(raw)!=a['sha256']:raise ReadinessError('Changed evidence: '+a['path'])
  captured[a['path']]=raw
 profiles={}
 for d,t in manifest['tasks'].items():
  for key in ('decision','horizon','permitted_features','availability_cutoff','target','unit_of_analysis','leakage_checks','evaluation_frame','usable_observation_count','limitations','readiness','real_time_validity','card_path','source_csv_path','csv_profile'):
   if key not in t or t[key] is None:raise ReadinessError('Missing task field: '+d+'/'+key)
  if t['card_path'] not in captured or t['source_csv_path'] not in captured:raise ReadinessError('Unbound task evidence')
  profile=csv_profile(captured[t['source_csv_path']],d)
  if profile!=t['csv_profile']:raise ReadinessError('Coverage changed: '+d)
  if t['real_time_validity']!='unresolved':raise ReadinessError('Phase7A did not recover qualifying forecast-date vintages')
  canonical_card=strict_json(captured[t['card_path']])
  if canonical_card!=t:raise ReadinessError('Task card/manifest claims differ')
  original=strict_json(captured[t['audit_card_path']])
  if original.get('domain')!=d:raise ReadinessError('Wrong audited domain card')
  if type(t['usable_observation_count']) is not int or t['usable_observation_count']!=(profile['three_period_eligible'] if d=='mas' else 0):raise ReadinessError('Impossible usable observation count')
  if t.get('agency_practical_margin') is not None:raise ReadinessError('Agency margin is pending')
  if d=='mas' and t.get('legacy_csv_path'):
   overlap=mas_overlap_profile(captured[t['legacy_csv_path']],captured[t['source_csv_path']])
   if overlap!=t['overlap_profile']:raise ReadinessError('MAS overlap comparability changed')
  profiles[d]=profile
 return {'schema':'mra-source-readiness-validation/1.0','successful':True,'validated_artifacts':len(paths),'domains':sorted(DOMAINS),'coverage':profiles,'benchmark_executed':False,'authorization_effect':'none','real_time_validity':{d:t['real_time_validity'] for d,t in manifest['tasks'].items()}}

def open_completed(root,store):
 store=Path(store);raw=(store/'source-readiness-manifest.json').read_bytes();done=strict_json((store/'completion.json').read_bytes())
 if done.get('manifest_sha256')!=sha(raw):raise ReadinessError('Manifest/completion binding changed')
 manifest=strict_json(raw);return raw,manifest,validate_manifest(Path(root),manifest)


def mas_overlap_profile(legacy_raw,archive_raw):
 old=checked_csv(legacy_raw.decode('utf-8-sig'))
 new=mas_archive_rows(archive_raw)
 months={name:i for i,name in enumerate(('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'),1)}
 indexed={}
 for r in new:
  if not re.fullmatch(r'\d{4} [A-Z][a-z]{2}',r.get('PERIOD','')):continue
  y,m=r['PERIOD'].split();indexed[f'{y}-{months[m]:02d}']=r
 fields={'cards_main':'NUMBER OF LOCAL CARDHOLDERS - MAIN *','cards_supplementary':'NUMBER OF LOCAL CARDHOLDERS - SUPPLEMENTARY *','total_billings':'S$ MILLION - TOTAL CARD BILLINGS','rollover_balance':'S$ MILLION - ROLLOVER BALANCE ^'}
 return {'overlap_months':len(old),'new_months':len(indexed)-len(old),'mismatches':{key:sum(Decimal(r[key])!=Decimal(indexed[r['month']][column]) for r in old) for key,column in fields.items()}}


def mas_archive_rows(raw):
 text=raw.decode('utf-8-sig')
 if not text.startswith('"MSB I.17 Credit and Charge Card Statistics (Discontinued from July 2019)"'):raise ReadinessError('Unexpected MAS table title')
 matrix=list(csv.reader(io.StringIO(text.split('\n',1)[1])))
 header=matrix[0];data=[]
 for row in matrix[1:]:
  if not row:continue
  if row==['The notes and footnotes for this table can be found on the online Monthly Statistical Bulletin database.']:continue
  if len(row)!=len(header):raise ReadinessError('Malformed MAS archive data width')
  if not re.fullmatch(r'\d{4} [A-Z][a-z]{2}',row[0]):raise ReadinessError('Unknown MAS archive nondata row')
  data.append(row)
 stream=io.StringIO();writer=csv.writer(stream);writer.writerow(header);writer.writerows(data)
 return checked_csv(stream.getvalue())
