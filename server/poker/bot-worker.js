'use strict';
const { parentPort } = require('node:worker_threads');
const { chooseAction } = require('./bot');
parentPort.on('message', ({ id, observation }) => {
  try { parentPort.postMessage({ id, decision: chooseAction(observation) }); }
  catch (error) { parentPort.postMessage({ id, error: error.message }); }
});
