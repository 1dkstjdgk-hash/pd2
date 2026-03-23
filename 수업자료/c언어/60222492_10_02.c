#include <stdio.h>
void main(){
	int num1,num2;
	printf("정수 2개를 입력하시오:");
	scanf("%d %d",&num1,&num2);
	int sum =0,i=1;
	while(i<=500){
		if(i%num1==0&&i%num2==0){
			sum += i;
		}i++;
	}printf("1~500사이의 정수 중 입력한 두수의 배수들의 총합:%d",sum);
}
