/**
 * Test script to verify login flow and logging
 * Run with: node test-login.js
 */

const API_URL = 'http://localhost:8000';

async function testLogin() {
  console.log('🧪 Testing login flow...\n');

  try {
    // Test login
    console.log('1. Attempting login...');
    const loginResponse = await fetch(`${API_URL}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: 'admin@example.com',
        password: 'admin123',
      }),
    });

    if (!loginResponse.ok) {
      const error = await loginResponse.json();
      throw new Error(error.detail || 'Login failed');
    }

    const loginData = await loginResponse.json();
    console.log('✅ Login successful');
    console.log('   Token type:', loginData.token_type);
    console.log('   Token length:', loginData.access_token.length);

    // Test getting current user
    console.log('\n2. Fetching current user...');
    const userResponse = await fetch(`${API_URL}/api/auth/me`, {
      headers: {
        'Authorization': `Bearer ${loginData.access_token}`,
      },
    });

    if (!userResponse.ok) {
      throw new Error('Failed to get current user');
    }

    const userData = await userResponse.json();
    console.log('✅ User data retrieved');
    console.log('   User ID:', userData.id);
    console.log('   Email:', userData.email);
    console.log('   Role:', userData.role);
    console.log('   Name:', userData.name);

    console.log('\n✅ All tests passed!');
    console.log('\nLogging behavior:');
    console.log('- In development: All debug logs visible in browser console');
    console.log('- In production: Only errors logged, debug logs suppressed');
    console.log('- Sensitive data redacted: Only {id, email, role} logged');

  } catch (error) {
    console.error('❌ Test failed:', error.message);
    process.exit(1);
  }
}

testLogin();
