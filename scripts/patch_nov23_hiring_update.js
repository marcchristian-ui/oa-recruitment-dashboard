// One-off: align snapshots/2026-11.json with the Hiring Update as of 23 Nov 2026
// (Manatal stages re-checked 23 Nov + Adaugeo EoW 20 Nov, Mirion start-date thread 19 Nov,
//  Ellie's Expected Joiners list 20 Nov, Mirion backfill JRF 20 Nov).
const fs = require('fs');
const P = 'snapshots/2026-11.json';
const s = JSON.parse(fs.readFileSync(P, 'utf8'));
const AS_OF = new Date('2026-11-23T00:00:00Z');
const days = d => Math.round((AS_OF - new Date(d + 'T00:00:00Z')) / 864e5);

const find = (name, hash) => {
  const r = s.closedWon.filter(c => c.candidate.toLowerCase().includes(name.toLowerCase()) && (!hash || c.jobHash === hash));
  if (r.length !== 1) throw new Error(`expected 1 match for ${name}/${hash}, got ${r.length}`);
  return r[0];
};
const set = (name, hash, fields) => Object.assign(find(name, hash), fields);

// Start dates / stages
set('Angelina', '8XR33R4R', { startDate: '2026-11-30', role: 'BILLING ANALYST' });
set('Oscar', 'X98R5V8R', { startDate: '2026-11-30' });
set('Marie Hail', null, { startDate: '2026-11-24', jobHash: '7X7YRY6X', jobHC: 1 });
set('Clariza', '5W7984R3', { startDate: '2027-01-07' });
set('Carla Ross', 'Y676VV35', { stage: 'Offer Accepted', startDate: '2026-12-10' });
set('JINO', 'Y676VV35', { stage: 'Offer Accepted', startDate: '2026-12-03' });
set('Renaliza', 'Y676VV35', { startDate: '2026-12-03' });
set('Joan Espinosa', 'Y676VV35', { startDate: '2026-12-03' });
set('Rodney', 'Y676VV35', { stage: 'Started', startDate: '2026-11-19' });
set('Earl', 'Y676VV35', { stage: 'Started', startDate: '2026-11-19' });
set('Patrich', 'Y676VV35', { stage: 'Started', startDate: '2026-11-19' });
set('Kenneth', 'Y676VV35', { startDate: '2026-11-25' }); // missed 19 Nov (hospitalised); 25 Nov proposed
for (const n of ['John Paul', 'Mary Grace', 'Braille', 'Mayce', 'Nonelyn']) set(n, 'Y676VV35', { startDate: '2026-12-10' }); // tentative, client to confirm by 24 Nov
set('Allysa', '5W8593W3', { startDate: '2026-11-05' });
set('Dianne', '5W8593W3', { startDate: '2026-11-05' });

// Kenneth was listed twice (Y676VV35 and 5W8593W3) -> one person, one seat
s.closedWon = s.closedWon.filter(c => !(c.candidate.includes('Kenneth') && c.jobHash === '5W8593W3'));

// Bryan Namli started 19 Nov (Manatal stage Started, Adaugeo EoW 20 Nov) but was missing
if (!s.closedWon.some(c => c.candidate.includes('Bryan'))) {
  s.closedWon.push({ client: 'ADAUGEO', role: 'CLINIC REFERRAL & PRIOR AUTHORIZATION', headcount: 1, openedDate: '2026-10-09', offerDate: '2026-10-23', startDate: '2026-11-19', timeToHire: 14, timeToFill: null, stage: 'Started', type: 'Ramp', candidate: 'Bryan Namli', jobHash: 'Y676VV35', jobHC: 13 });
}

// Second Adaugeo withdrawal (Marionette C., 3 Dec batch, 13 Nov)
if (!s.withdrawals.some(w => w.candidate.includes('Marionette'))) {
  s.withdrawals.push({ client: 'ADAUGEO', role: 'CLINIC REFERRAL & PRIOR AUTHORIZATION', headcount: 1, openedDate: '2026-10-09', offerDate: '2026-10-23', withdrawnDate: '2026-11-13', priorStage: 'Offer Accepted', type: 'Ramp', candidate: 'Marionette C.', reason: 'Candidate withdrew after accepting offer', jobHash: 'Y676VV35', jobHC: 13 });
}

// New Mirion Billing Analyst backfill opened 20 Nov (Y677VVX5)
const newJob = { role: 'BILLING ANALYST', client: 'MIRION (NUCMED)', type: 'Backfill', opened: '2026-11-20', days: 3, headcount: 1, hash: 'Y677VVX5' };
if (!s.aging.jobs.some(j => j.hash === 'Y677VVX5')) {
  s.aging.jobs.push({ ...newJob });
  s.business.backfillJobs.push({ ...newJob });
  s.business.backfillCount += 1;
  s.additionalInMonth += 1; s.additionalInMonthRoles += 1;
  s.activeRequisitions += 1; s.activeRequisitionsRoles += 1;
}

// Re-age everything to 23 Nov
for (const list of [s.aging.jobs, s.business.newLogoJobs, s.business.rampJobs, s.business.backfillJobs]) for (const j of list) j.days = days(j.opened);
for (const j of s.somCarryOver) j.days = days(j.opened);
const avg = t => { const a = s.aging.jobs.filter(j => j.type === t); return a.length ? Math.round(a.reduce((x, j) => x + j.days, 0) / a.length) : 0; };
s.aging.avgNewLogo = avg('New Logo'); s.aging.avgRamp = avg('Ramp'); s.aging.avgBackfill = avg('Backfill');
const b = { fresh: 0, normal: 0, aging: 0, critical: 0 };
for (const j of s.aging.jobs) b[j.days <= 14 ? "fresh" : j.days <= 45 ? "normal" : j.days <= 60 ? "aging" : "critical"] += j.headcount;
Object.assign(s.aging, b);

// Pipeline counts (headcount)
const hc = st => s.closedWon.filter(c => c.stage === st).reduce((x, c) => x + (c.headcount || 1), 0);
s.totalOpen = s.aging.jobs.reduce((x, j) => x + j.headcount, 0);
s.pipeline.open = s.totalOpen;
s.pipeline.started = hc('Started');
s.pipeline.offerAccepted = hc('Offer Accepted');
s.pipeline.forJobOffer = s.inOfferRoles.reduce((x, r) => x + (r.headcount || 1), 0);
s.pipeline.ongoingContract = s.ongoingContractRoles.reduce((x, r) => x + (r.headcount || 1), 0);

fs.writeFileSync(P, JSON.stringify(s, null, 2) + '\n');
console.log({ totalOpen: s.totalOpen, pipeline: s.pipeline, closedWon: s.closedWon.length, aging: { ...b, avgNewLogo: s.aging.avgNewLogo, avgRamp: s.aging.avgRamp, avgBackfill: s.aging.avgBackfill }, add: s.additionalInMonth, withdrawals: s.withdrawals.length });
