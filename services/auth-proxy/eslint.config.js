// The globals this relay's own source uses, and nothing else: the shape
// and the rules are `../eslint.config.base.mjs`.
//
// The shortest of the three lists, because this relay forwards two
// requests and reads no body: it needs no crypto, no encoder and no
// timeout signal.
import { relayConfig } from '../eslint.config.base.mjs';

export default [relayConfig()];
