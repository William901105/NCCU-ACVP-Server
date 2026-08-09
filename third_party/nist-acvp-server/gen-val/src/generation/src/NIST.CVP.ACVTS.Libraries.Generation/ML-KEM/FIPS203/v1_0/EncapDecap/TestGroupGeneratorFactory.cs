using System.Collections.Generic;
using NIST.CVP.ACVTS.Libraries.Generation.Core;

namespace NIST.CVP.ACVTS.Libraries.Generation.ML_KEM.FIPS203.v1_0.EncapDecap;

public class TestGroupGeneratorFactory : ITestGroupGeneratorFactory<Parameters, TestGroup, TestCase>
{
    public IEnumerable<ITestGroupGeneratorAsync<Parameters, TestGroup, TestCase>> GetTestGroupGenerators(Parameters parameters)
    {
        var list = new HashSet<ITestGroupGeneratorAsync<Parameters, TestGroup, TestCase>>
        {
            new TestGroupGeneratorEncapsulationAft(),
            new TestGroupGeneratorDecapsulationVal(),
            new TestGroupGeneratorKeyCheckVal()
        };

        return list;
    }
}
