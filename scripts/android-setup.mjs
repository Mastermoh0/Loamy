// Registers the com.loamy.app:// deep-link scheme on the generated Android
// project so Google OAuth can return to the app. Run after `npx cap add android`.
import { readFileSync, writeFileSync, existsSync } from "node:fs";

const manifestPath = "android/app/src/main/AndroidManifest.xml";
const scheme = "com.loamy.app";

if (!existsSync(manifestPath)) {
  console.error(`${manifestPath} not found. Run "npx cap add android" first.`);
  process.exit(1);
}

const manifest = readFileSync(manifestPath, "utf8");

if (manifest.includes(`android:scheme="${scheme}"`)) {
  console.log("Deep-link intent filter already present, skipping.");
  process.exit(0);
}

const intentFilter = `
            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="${scheme}" />
            </intent-filter>
        `;

const closingTag = "</activity>";
const index = manifest.indexOf(closingTag);
if (index === -1) {
  console.error("Could not find </activity> in AndroidManifest.xml.");
  process.exit(1);
}

writeFileSync(manifestPath, manifest.slice(0, index) + intentFilter + manifest.slice(index));
console.log(`Added ${scheme}:// intent filter to MainActivity.`);
