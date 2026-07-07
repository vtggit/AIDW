module.exports = {
    testDir: '.',
    reporter: [['junit', { outputFile: 'report.xml' }], ['list']],
    use: {
        baseURL: process.env.BASE_URL || 'http://localhost:8080',
    },
};
