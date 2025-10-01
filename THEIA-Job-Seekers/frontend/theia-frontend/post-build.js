#!/usr/bin/env node

/**
 * THEIA Post-Build Script
 * Ensures production-ready configuration after React build
 * This script runs automatically after every 'npm run build'
 */

const fs = require('fs');
const path = require('path');

console.log('🔧 THEIA Post-Build: Ensuring production configuration...');

const buildDir = path.join(__dirname, 'build');
const backendUrl = process.env.REACT_APP_API_URL || 'https://theia-backend-v2-603965392227.us-central1.run.app';

// 1. Ensure api-base.txt exists with correct backend URL
const apiBasePath = path.join(buildDir, 'api-base.txt');
fs.writeFileSync(apiBasePath, backendUrl);
console.log(`✅ Created api-base.txt with: ${backendUrl}`);

// 2. Verify index.html has correct API base loading
const htmlFiles = ['index.html'];

htmlFiles.forEach(filename => {
    const filepath = path.join(buildDir, filename);
    if (fs.existsSync(filepath)) {
        let content = fs.readFileSync(filepath, 'utf8');
        
        // Check for hardcoded localhost and warn if found
        if (content.includes('const API_BASE = \'http://localhost:8000\'')) {
            console.log(`⚠️  WARNING: ${filename} still has hardcoded localhost API_BASE`);
            console.log(`   This should be fixed in the source file: public/${filename}`);
        } else if (content.includes('resolveApiBase') && content.includes('loadApiBase')) {
            console.log(`✅ ${filename} has correct API base loading`);
        } else {
            console.log(`⚠️  WARNING: ${filename} may not have proper API base configuration`);
        }
        // Voice token fallback is handled by the SPA; no index.html checks needed
        
        // Ensure no absolute paths in redirects
        const absolutePaths = content.match(/href="\/[^"]*"|window\.location[^=]*="\/[^"]*"/g);
        if (absolutePaths) {
            console.log(`⚠️  WARNING: ${filename} has absolute paths that may cause issues:`);
            absolutePaths.forEach(path => console.log(`   ${path}`));
        } else {
            console.log(`✅ ${filename} has no problematic absolute paths`);
        }
    }
});

// 3. Ensure required directories exist
const requiredDirs = ['styles', 'public'];
requiredDirs.forEach(dir => {
    const dirPath = path.join(buildDir, dir);
    if (fs.existsSync(dirPath)) {
        console.log(`✅ Directory exists: ${dir}/`);
    } else {
        console.log(`⚠️  Missing directory: ${dir}/`);
    }
});

// 4. Check for required assets and fix ISA portrait if needed
const requiredAssets = [
    'styles/theme.css',
    'public/THEIA-logo.png',
    'public/user-icon.svg',
    'isa_portrait.png',
    'favicon.ico'
];

requiredAssets.forEach(asset => {
    const assetPath = path.join(buildDir, asset);
    if (fs.existsSync(assetPath)) {
        const stats = fs.statSync(assetPath);
        console.log(`✅ Asset exists: ${asset} (${stats.size} bytes)`);
        
        // Special check for ISA portrait - if it's 0 bytes, fix it
        if (asset === 'isa_portrait.png' && stats.size === 0) {
            console.log('🔧 Fixing empty ISA portrait file...');
            const correctFile = path.join(__dirname, 'public', 'isa_portrait.png');
            if (fs.existsSync(correctFile)) {
                fs.copyFileSync(correctFile, assetPath);
                console.log('✅ ISA portrait fixed');
            }
        }
    } else {
        console.log(`❌ Missing asset: ${asset}`);
    }
});

// IMPORTANT: Respect legacy index.html unified preprocessing page copied at deploy time.
// Do not overwrite build/index.html with a redirect anymore.

// No extra legacy HTML validation; SPA handles API base discovery

console.log('🎉 THEIA Post-Build completed successfully!');
console.log('📋 Build is ready for deployment to Google Cloud Storage');
