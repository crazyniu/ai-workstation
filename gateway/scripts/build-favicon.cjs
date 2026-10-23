#!/usr/bin/env node
// Optional asset-authoring tool. The generated files are checked in, so normal
// builds do not require Node or this renderer. See CONTRIBUTING.md.
const { Resvg } = require('@resvg/resvg-js');
const fs = require('node:fs');
const path = require('node:path');

const web = path.resolve(__dirname, '../web');
const source = fs.readFileSync(path.join(web, 'favicon.svg'));
const render = size => new Resvg(source, { fitTo: { mode: 'width', value: size } }).render().asPng();
const sizes = [16, 32, 48];
const frames = sizes.map(render);
const header = Buffer.alloc(6 + sizes.length * 16);
header.writeUInt16LE(1, 2); // ICO image type
header.writeUInt16LE(sizes.length, 4);
let offset = header.length;
frames.forEach((frame, index) => {
  const entry = 6 + index * 16;
  header[entry] = header[entry + 1] = sizes[index];
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(frame.length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += frame.length;
});
fs.writeFileSync(path.join(web, 'favicon.ico'), Buffer.concat([header, ...frames]));
fs.writeFileSync(path.join(web, 'favicon-32.png'), frames[1]);
fs.writeFileSync(path.join(web, 'apple-touch-icon.png'), render(180));
