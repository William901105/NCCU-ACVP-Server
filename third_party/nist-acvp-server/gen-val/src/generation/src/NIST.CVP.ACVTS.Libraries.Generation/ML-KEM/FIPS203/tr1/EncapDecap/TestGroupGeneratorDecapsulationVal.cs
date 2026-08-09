using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.MLKEM;
using NIST.CVP.ACVTS.Libraries.Generation.Core;
using NIST.CVP.ACVTS.Libraries.Generation.ML_KEM.FIPS203.tr1.EncapDecap.TestCaseExpectations;

namespace NIST.CVP.ACVTS.Libraries.Generation.ML_KEM.FIPS203.tr1.EncapDecap;

public class TestGroupGeneratorDecapsulationVal : ITestGroupGeneratorAsync<Parameters, TestGroup, TestCase>
{
public Task<List<TestGroup>> BuildTestGroupsAsync(Parameters parameters)
    {
        var testGroups = new List<TestGroup>();
        
        foreach (var parameterSet in parameters.ParameterSets.Distinct())
        {
            if (parameters.Functions.Contains(MLKEMFunction.Decapsulation))
            {
                foreach (var keyFormat in parameters.KeyFormats.Distinct())
                {
                    var testGroup = new TestGroup
                    {
                        TestType = "VAL",
                        Function = MLKEMFunction.Decapsulation,
                        ParameterSet = parameterSet,
                        DecapsulationExpectationProvider = new DecapsulationExpectationProvider(),
                        KeyFormat = keyFormat
                    };
                    
                    testGroups.Add(testGroup);
                }
            }
        }

        return Task.FromResult(testGroups);
    }
}
