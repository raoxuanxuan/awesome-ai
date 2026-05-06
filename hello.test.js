import { hello } from './hello.js';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(hello('World') === 'Hello, World!', 'hello should return greeting');
assert(hello('AI') === 'Hello, AI!', 'hello should work with AI');

console.log('All tests passed');
