const { useState, useEffect } = React;

const WebGUI = () => {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [modules, setModules] = useState({});
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    if (isLoggedIn) {
      fetchModules();
      const interval = setInterval(fetchModules, 5000);
      return () => clearInterval(interval);
    }
  }, [isLoggedIn]);

  const fetchModules = async () => {
    try {
      const response = await fetch('/api/modules', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setModules(data);
      }
    } catch (err) {
      setError('Failed to fetch modules');
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('token', data.token);
        setIsLoggedIn(true);
        setError('');
      } else {
        setError('Invalid credentials');
      }
    } catch (err) {
      setError('Login failed');
    }
  };

  const handleServerShutdown = async () => {
        // Show confirmation dialog
        if (!window.confirm('Are you sure you want to shut down the server? This will disconnect all clients.')) {
            return;
        }

        try {
            setSuccess('Initiating server shutdown...');

            const response = await fetch('/api/server/shutdown', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                }
            });

            if (response.ok) {
                setSuccess('Server is shutting down. You will be disconnected shortly.');
                // Clear login state after brief delay
                setTimeout(() => {
                    setIsLoggedIn(false);
                    localStorage.removeItem('token');
                    // Show final message
                    alert('Server has been shut down. You can close this window.');
                }, 2000);
            } else {
                setError('Failed to shutdown server');
            }
        } catch (err) {
            // If we got a network error, it might mean the server is already shutting down
            setSuccess('Server connection lost. The server is likely shutting down.');
            setTimeout(() => {
                setIsLoggedIn(false);
                localStorage.removeItem('token');
                alert('Server has been shut down. You can close this window.');
            }, 1000);
        }
    };

  const handleModuleAction = async (moduleName, action) => {
    try {
      const response = await fetch(`/api/modules/${moduleName}/action`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ action })
      });

      if (response.ok) {
        setSuccess(`Successfully ${action}d ${moduleName}`);
        fetchModules();
      } else {
        setError(`Failed to ${action} ${moduleName}`);
      }
    } catch (err) {
      setError(`Failed to ${action} ${moduleName}`);
    }
  };

  if (!isLoggedIn) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="bg-white p-8 rounded-lg shadow-md w-96">
          <h1 className="text-2xl font-bold mb-6 text-center">DracoSoft Server Manager</h1>
          {error && (
            <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4">
              <div className="flex items-center">
                <i className="fas fa-exclamation-circle text-red-500 mr-2"></i>
                <p className="text-red-700">{error}</p>
              </div>
            </div>
          )}
          <form onSubmit={handleLogin}>
            <div className="mb-4">
              <label className="block text-sm font-medium mb-1">Username</label>
              <input
                type="text"
                className="w-full p-2 border rounded"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="mb-6">
              <label className="block text-sm font-medium mb-1">Password</label>
              <input
                type="password"
                className="w-full p-2 border rounded"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className="w-full bg-blue-600 text-white p-2 rounded hover:bg-blue-700"
            >
              Login
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-bold">Module Status</h1>
            <button
              onClick={() => fetchModules()}
              className="bg-blue-600 text-white p-2 rounded hover:bg-blue-700"
              title="Refresh"
            >
              <i className="fas fa-sync-alt"></i>
            </button>
          </div>
          <button
            onClick={handleServerShutdown}
            className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700 flex items-center gap-2"
          >
            <i className="fas fa-power-off"></i>
            Shutdown Server
          </button>
        </div>

        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4">
            <div className="flex items-center">
              <i className="fas fa-exclamation-circle text-red-500 mr-2"></i>
              <p className="text-red-700">{error}</p>
            </div>
          </div>
        )}

        {success && (
          <div className="bg-green-50 border-l-4 border-green-500 p-4 mb-4">
            <div className="flex items-center">
              <i className="fas fa-check-circle text-green-500 mr-2"></i>
              <p className="text-green-700">{success}</p>
            </div>
          </div>
        )}

        <div className="grid gap-4">
          {Object.entries(modules).map(([name, info]) => (
            <div key={name} className="bg-white p-4 rounded-lg shadow">
              <div className="flex justify-between items-center">
                <div>
                  <h2 className="text-lg font-semibold">{name}</h2>
                  <p className="text-sm text-gray-600">Version: {info.version}</p>
                  <p className={`text-sm ${
                    info.state === 'ENABLED' ? 'text-green-600' : 'text-red-600'
                  }`}>
                    Status: {info.state}
                  </p>
                </div>
                <div className="flex gap-2">
                  {info.state === 'ENABLED' ? (
                    <button
                      onClick={() => handleModuleAction(name, 'disable')}
                      className="bg-red-600 text-white p-2 rounded hover:bg-red-700"
                    >
                      <i className="fas fa-power-off"></i>
                    </button>
                  ) : (
                    <button
                      onClick={() => handleModuleAction(name, 'enable')}
                      className="bg-green-600 text-white p-2 rounded hover:bg-green-700"
                    >
                      <i className="fas fa-power-off"></i>
                    </button>
                  )}
                  <button
                    onClick={() => handleModuleAction(name, 'restart')}
                    className="bg-yellow-600 text-white p-2 rounded hover:bg-yellow-700"
                  >
                    <i className="fas fa-sync-alt"></i>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// Render the app
ReactDOM.render(<WebGUI />, document.getElementById('root'));