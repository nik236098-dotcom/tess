'use strict';
const { Worker } = require('node:worker_threads');
const path = require('node:path');

// Shared bounded pool: adding seats never creates an unbounded number of
// workers. Cancellation discards queued/stale turns; workers see public data.
const slots = [];
const queue = [];
let sequence = 0;
function pump() {
  while (queue.length) {
    let slot = slots.find(s => !s.job);
    if (!slot && slots.length < 2) {
      slot = { worker: new Worker(path.join(__dirname, 'bot-worker.js')), job: null };
      slots.push(slot);
      const finish = (error, data) => {
        const job = slot.job;
        if (!job) return;
        slot.job = null;
        clearTimeout(job.timeout);
        if (error) job.reject(error); else job.resolve(data.decision);
        slot.worker.unref();
        pump();
      };
      slot.worker.on('message', data => {
        if (data.id === slot.job?.id) finish(data.error ? new Error(data.error) : null, data);
      });
      slot.worker.on('error', error => {
        const index = slots.indexOf(slot);
        if (index >= 0) slots.splice(index, 1);
        finish(error);
      });
      slot.worker.unref();
    }
    if (!slot) return;
    const job = queue.shift();
    if (job.signal.aborted) continue;
    slot.job = job;
    slot.worker.ref();
    job.timeout = setTimeout(() => {
      const index = slots.indexOf(slot);
      if (index >= 0) slots.splice(index, 1);
      slot.job = null;
      slot.worker.terminate();
      job.reject(new Error('Bot calculation timed out'));
      pump();
    }, 4000);
    slot.worker.postMessage({ id: job.id, observation: job.observation });
  }
}

function runBot(observation, signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new Error('Cancelled'));
    if (queue.length >= 64) return reject(new Error('Bot queue full'));
    const abort = () => {
      const index = queue.indexOf(job);
      if (index >= 0) queue.splice(index, 1);
      reject(new Error('Cancelled'));
    };
    const settle = fn => value => { signal.removeEventListener('abort', abort); fn(value); };
    const job = { id: ++sequence, observation, signal, resolve: settle(resolve), reject: settle(reject) };
    signal.addEventListener('abort', abort, { once: true });
    queue.push(job);
    pump();
  });
}
module.exports = { runBot };
