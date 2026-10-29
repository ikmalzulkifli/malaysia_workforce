import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
import { transformIdentity } from '../build_hrms.mjs'

const root = process.env.HRMS_FRONTEND || path.resolve('apps/hrms/frontend')
const require = createRequire(path.join(root, 'package.json'))
const { parse, compileScript, compileTemplate } = require('@vue/compiler-sfc')
const files = [
  ['src/components/BaseLayout.vue', '__("Frappe HR")'],
  ['src/components/InstallPrompt.vue', '__("Install Frappe HR")'],
  ['src/views/Login.vue', '__("Login to Frappe HR")'],
]
for (const [relative, nativeLabel] of files) {
  test(`compiles ${relative} with setup binding and native fallback`, async () => {
    const id = path.join(root, relative)
    const original = await readFile(id, 'utf8')
    const transformed = transformIdentity(original, id, root).code
    assert.ok(transformed.includes(nativeLabel))
    assert.ok(transformed.includes('const ocean6Brand = document.documentElement.dataset.ocean6Brand'))
    if (relative.endsWith('Login.vue')) {
      assert.match(transformed, /<FrappeHRLogo v-else/)
      assert.match(transformed, /ocean6Brand && ocean6EmailLink/)
      assert.match(transformed, /redirect-to=%2Fhrms%2Fhome#login-with-email-link/)
      assert.match(transformed, /ocean6-hrms-login-submit/)
      assert.match(transformed, /ocean6-hrms-login-brand/)
      assert.match(transformed, /ocean6-hrms-login/)
    }
    const parsed = parse(transformed, { filename: id })
    assert.deepEqual(parsed.errors, [])
    const script = compileScript(parsed.descriptor, { id: 'ocean6-test' })
    const template = compileTemplate({ source: parsed.descriptor.template.content, filename: id, id: 'ocean6-test', compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [])
    assert.match(template.code, /\$setup\.ocean6Brand/)
    assert.doesNotMatch(template.code, /_ctx\.(globalThis|document|ocean6Brand)/)
    assert.throws(() => transformIdentity(transformed, id, root), /already exists/)
    assert.throws(() => transformIdentity(original.replace(nativeLabel, 'changed'), id, root), /expected/)
  })
}
test('ignores subrequests and unrelated paths', () => {
  assert.equal(transformIdentity('', path.join(root, files[0][0]) + '?vue', root), null)
  assert.equal(transformIdentity('', '/other/src/views/Login.vue', root), null)
})
